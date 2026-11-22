"""The watchdog of "Als Oma jung war": keeps one video a week going with nobody watching (watchdog.yml).

Each pass (every 15 minutes inside a ~5.5 h run that starts its successor):
  1. a failed episode run: no retry when it stopped on a quota / 429 / deliberate stop; otherwise its failed jobs
     are rerun, and a topic whose builds fail twice is skipped (queue "skipped"); at most ONE attempt per topic
     per day (state/watchdog.json "attempts"); exit 3 of the build (not enough pictures) skips the topic at once
  2. stock: videos waiting (scheduled in the future + built) must be 2, plus 1-2 emergency reserve (uploaded private,
     no date). Below that, and with no run going, the next topic is built (its script is written ahead by
     scripts-de.yml; a topic without one is written first). Nothing starts without both LLM keys
  3. EMERGENCY: when the next Sunday 17:00 slot is less than 24 h away and no video of the channel holds it, a reserve
     video is scheduled into it (private -> publishAt). Nothing empty goes unanswered if a reserve exists
  4. a built episode that could not be uploaded (doubt, no token yet) is uploaded again, once a day
  5. state/heartbeat.json is committed once a day, so GitHub never turns the schedule off
No mail is ever sent (owner 21.11): what needs a person stays in state/watchdog.json and the run log.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from automation import quota_hold  # noqa: E402

CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))
REPO = os.environ.get("GITHUB_REPOSITORY", "beautyapp800-ctrl/germany-archive-channel")
STATE, QUEUE = ROOT / "state" / "episodes.json", ROOT / "topics" / "queue.json"
MEM, BEAT = ROOT / "state" / "watchdog.json", ROOT / "state" / "heartbeat.json"
AHEAD = CFG["schedule"]["ahead"]
RESERVE_MIN, RESERVE_MAX = CFG["schedule"]["emergency_reserve"]
TOPIC_FAILS = 2


def now():
    return datetime.now(timezone.utc)


def z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def gh(*args, parse=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return json.loads(r.stdout) if parse and r.stdout.strip() else r.stdout


def load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(p, obj, indent=1):
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def runs(wf):
    return gh("api", f"repos/{REPO}/actions/workflows/{wf}/runs?per_page=10")["workflow_runs"]


def run_slug(run):
    t = (run.get("display_title") or "").split()
    return t[-1] if len(t) > 1 else ""


def log_of(run_id, failed=True):
    r = subprocess.run(["gh", "run", "view", str(run_id), "-R", REPO, "--log-failed" if failed else "--log"],
                       capture_output=True, text=True)
    return r.stdout or ""


def attempt_allowed(mem, slug):
    """One attempt per topic per day (a quota stop does not count: it waits for the quota day)."""
    return not any(a.startswith(f"{now():%Y-%m-%d}") for a in mem.setdefault("attempts", {}).get(slug, []))


def record_attempt(mem, slug):
    mem.setdefault("attempts", {}).setdefault(slug, []).append(z(now()))


def set_topic(slug, **kw):
    q = load(QUEUE, {"topics": []})
    for t in q["topics"]:
        if t["slug"] == slug:
            t.update(kw)
    save(QUEUE, q)


def handle_failed_run(last, mem, actions):
    """True when this run is dealt with (a rerun was started or the topic left)."""
    slug = run_slug(last)
    text = log_of(last["id"])
    if "NOT_ENOUGH_PICTURES" in text:
        set_topic(slug, status="skipped", skipped_why="not enough fresh pictures after the frame check")
        actions.append(f"{slug} skipped: not enough fresh pictures; the next topic follows")
        return False
    if any(m in text for m in ("429", "VISION_QUOTA_SPENT", "TEXT_DAY_SPENT", "was cancelled", "deliberate stop")):
        key = f"stop-{last['id']}"
        if key not in mem.setdefault("noted", []):
            mem["noted"].append(key)
            actions.append(f"{slug}: run {last['id']} stopped on a quota/429/cancel; not retried")
        return True
    fails = mem.setdefault("topic_fails", {})
    if last.get("run_attempt", 1) < 2 and attempt_allowed(mem, slug):
        try:
            gh("run", "rerun", str(last["id"]), "-R", REPO, "--failed", parse=False)
        except RuntimeError:
            gh("run", "rerun", str(last["id"]), "-R", REPO, parse=False)
        record_attempt(mem, slug)
        actions.append(f"{slug}: failed jobs of run {last['id']} rerun")
        return True
    key = f"run-{last['id']}"
    if key not in mem.setdefault("noted", []):
        mem["noted"].append(key)
        fails[slug] = fails.get(slug, 0) + 1
        if fails[slug] >= TOPIC_FAILS:
            set_topic(slug, status="skipped", skipped_why=f"its build failed {fails[slug]} times, last run {last['id']}")
            actions.append(f"{slug} skipped after {fails[slug]} failed builds")
        else:
            actions.append(f"{slug}: build failed (run {last['id']}); one new attempt tomorrow")
    return False


def stock(rows):
    t = z(now())
    waiting = [r for r in rows if r.get("state") == "built" or
               (r.get("state") == "scheduled" and (r.get("publish_at") or "") > t)]
    reserve = [r for r in rows if r.get("state") == "reserve"]
    return waiting, reserve


def next_sunday_slot():
    """The next Sunday 17:00 Berlin, whatever the lead time."""
    tz = ZoneInfo(CFG["schedule"]["timezone"])
    hh, mm = (int(x) for x in CFG["schedule"]["local_time"].split(":"))
    d = now().astimezone(tz).date()
    for _ in range(14):
        s = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
        if s.weekday() in CFG["schedule"]["weekdays"] and s.astimezone(timezone.utc) > now():
            return s.astimezone(timezone.utc)
        d += timedelta(days=1)


def emergency(rows, actions):
    """A slot under 24 h away that no video holds gets a reserve video."""
    if not os.environ.get("YT_TOKEN_JSON"):
        return
    from core import ytguard
    from pipeline import youtube
    slot = next_sunday_slot()
    if slot - now() > timedelta(hours=24):
        return
    try:
        yt = youtube.service()
        ytguard.check_channel(yt, os.environ.get("YT_CHANNEL_ID") or CFG.get("youtube_channel_id"))
        videos = youtube.all_uploads(yt, [r["youtube_id"] for r in rows if r.get("youtube_id")])
    except Exception as e:                                           # noqa: BLE001
        actions.append(f"slot {z(slot)} not checked, not sure about the channel: {str(e)[:120]}")
        return
    held = [d for d in youtube.channel_dates(videos)
            if abs((datetime.fromisoformat(d.replace("Z", "+00:00")) - slot).total_seconds()) < 12 * 3600]
    if held:
        return
    reserve = [r for r in rows if r.get("state") == "reserve" and r.get("youtube_id")]
    if not reserve:
        actions.append(f"EMPTY SLOT {z(slot)} and no reserve video; nothing to post")
        return
    r = reserve[0]
    youtube.schedule(r["youtube_id"], slot, yt=yt)
    r.update(state="scheduled", publish_at=z(slot), emergency=True)
    save(STATE, rows)
    actions.append(f"EMERGENCY: reserve {r['slug']} ({r['youtube_id']}) scheduled into the empty slot {z(slot)}")


def thumbnails(rows, mem, actions):
    """A cover YouTube refused (new channel, not verified yet) is tried again once a day."""
    if not os.environ.get("YT_TOKEN_JSON"):
        return
    for r in rows:
        f = ROOT / "episodes" / r["slug"] / "thumbnail.jpg"
        if r["slug"] in CFG["upload"].get("keep_auto_thumbnail", []):
            continue                      # owner 22.11: this video keeps YouTube's automatic frame
        if not (str(r.get("thumbnail", "")).startswith("failed") and r.get("youtube_id") and f.exists()):
            continue
        if not attempt_allowed(mem, "thumb-" + r["slug"]):
            continue
        record_attempt(mem, "thumb-" + r["slug"])
        try:
            from pipeline import youtube
            youtube.set_thumbnail(r["youtube_id"], f)
            r["thumbnail"] = "ok"
            save(STATE, rows)
            actions.append(f"{r['slug']}: thumbnail set")
        except Exception as e:                                       # noqa: BLE001
            r["thumbnail_note"] = str(e)[:120]
            save(STATE, rows)


def main():
    mem = load(MEM, {"attempts": {}, "noted": []})
    actions = []
    rows = load(STATE, [])
    keys = os.environ.get("KEYS_READY") == "true"
    ep = runs("episode-de.yml")
    sc = runs("scripts-de.yml")
    busy = any(r["status"] != "completed" for r in ep + sc)
    last = next((r for r in ep if r["status"] == "completed"), None)
    if not busy and last and last["conclusion"] in ("failure", "timed_out"):
        busy = handle_failed_run(last, mem, actions) or busy
    emergency(rows, actions)
    # uploads that did not happen in the release job
    if os.environ.get("YT_TOKEN_JSON"):
        for r in rows:
            if r.get("state") == "built" and not r.get("youtube_id") and r.get("run_id") and attempt_allowed(mem, "up-" + r["slug"]):
                gh("workflow", "run", "upload.yml", "-R", REPO, "-f", f"slug={r['slug']}", "-f", f"run_id={r['run_id']}",
                   parse=False)
                record_attempt(mem, "up-" + r["slug"])
                actions.append(f"{r['slug']}: built but not on YouTube; upload started again")
                busy = True
    thumbnails(rows, mem, actions)
    waiting, reserve = stock(rows)
    want = len(waiting) < AHEAD or len(reserve) < RESERVE_MIN
    if want and len(waiting) + len(reserve) < AHEAD + RESERVE_MAX and not busy:
        if not keys:
            actions.append("waiting for GROQ_API_KEY_AR and GEMINI_API_KEY_AR; no build started")
        elif quota_hold.active(now()):
            actions.append("the text providers' day is held; nothing started")
        else:
            q = load(QUEUE, {"topics": []})
            ready = next((t for t in q["topics"] if t.get("status") == "ready"
                          and (ROOT / "episodes" / t["slug"] / "script.json").exists()), None)
            if ready and attempt_allowed(mem, ready["slug"]):
                gh("workflow", "run", "episode-de.yml", "-R", REPO, "--ref", "main", "-f", f"slug={ready['slug']}", parse=False)
                record_attempt(mem, ready["slug"])
                actions.append(f"stock {len(waiting)} waiting + {len(reserve)} reserve; {ready['slug']} started")
            elif not ready and sum(a.startswith(f"{now():%Y-%m-%d}") for a in mem.get("attempts", {}).get("scripts", [])) < 4:
                record_attempt(mem, "scripts")
                gh("workflow", "run", "scripts-de.yml", "-R", REPO, "--ref", "main", parse=False)
                actions.append(f"stock {len(waiting)} waiting + {len(reserve)} reserve; no script ready, writing one")
    old = load(BEAT, {})
    beat = {"date": f"{now():%Y-%m-%d}", "checked_at": z(now()),
            "waiting": [[r["slug"], r.get("state"), r.get("publish_at")] for r in waiting],
            "reserve": [r["slug"] for r in reserve], "actions": actions}
    save(BEAT, beat)
    save(MEM, mem)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"commit={'true' if actions or old.get('date') != beat['date'] else 'false'}\n")
    print(json.dumps(beat, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
