"""After a build: the episode goes to YouTube, or into the buffer ("Als Oma jung war").

    python automation/release.py record <slug>     # after QA: buffer it; upload if a token exists
    python automation/release.py upload            # every buffered episode, once a token exists
    python automation/release.py dry [slug]        # read the channel in full, say what would happen

state/episodes.json holds every episode:
  built       rendered, QA passed, in the buffer (files in the build run's artifact)
  scheduled   uploaded private with a publishAt (Sunday 17:00 Berlin)
  published   its publishAt has passed
  qa-failed   the QA gate refused it; nothing was uploaded
  reserve     uploaded private, no slot: the emergency reserve the watchdog schedules when a slot is empty

Nothing is uploaded without a passing QA report (episodes/<slug>/out/qa.json). One episode, one
video: the channel is asked first (the complete uploads list, marker "[ref: germany/<slug>]") and the
id is committed to git the moment YouTube returns it (persist); in doubt nothing is uploaded. No
mail is ever sent (owner 21.11): what needs a human stays in the run log and the state file.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.logger import get_logger  # noqa: E402
from pipeline import youtube  # noqa: E402

log = get_logger("release")
STATE = ROOT / "state" / "episodes.json"
CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))


def _now_z():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else []


def save(r):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")


def row_of(r, slug):
    row = next((x for x in r if x["slug"] == slug), None)
    if row is None:
        row = {"slug": slug}
        r.append(row)
    return row


def notify(subject, body):
    """No mail to the owner (21.11): the text stays in the Actions log."""
    log.error("NOTE: %s | %s", subject, body)


def persist(message):
    """Owner 17.11: the record of a video is in git at once, or the run fails (it used to be lost:
    `git add a b || true` added nothing when b did not exist, and the topic was built and
    uploaded again). Only in Actions; locally the file is just written."""
    if not os.environ.get("GITHUB_ACTIONS") or os.environ.get("DRY_RUN") or os.environ.get("NO_PERSIST"):
        return
    import subprocess
    import time

    def git(*a, check=True):
        return subprocess.run(["git", *a], capture_output=True, text=True, check=check)
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for f in ("state/episodes.json", "topics/queue.json", "state/usage.json"):
        if (ROOT / f).exists():
            git("add", f)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    git("commit", "-q", "-m", message)
    last = ""
    for i in range(5):
        r = git("pull", "-q", "--rebase", "--autostash", "origin", "main", check=False)
        if r.returncode == 0:
            r = git("push", "-q", "origin", "HEAD:main", check=False)
            if r.returncode == 0:
                log.info("state committed: %s", message)
                return
        last = (r.stderr or r.stdout or "")[-300:]
        time.sleep(8 * (i + 1))
    notify("The state of a video could not be saved to git",
           f"{message}\n{last}\nThe run fails; the video is on YouTube.")
    raise RuntimeError(f"the state could not be committed: {last}")


def _slot(videos, r):
    taken = [x["publish_at"] for x in r if x.get("publish_at")] + youtube.channel_dates(videos)
    when = youtube.next_slot(taken)
    if os.environ.get("PUBLISH_AT"):                     # upload.yml publish_at: a slot given by hand
        from datetime import datetime
        when = datetime.fromisoformat(os.environ["PUBLISH_AT"].replace("Z", "+00:00"))
    return when


def _upload(slug, r):
    out = ROOT / "episodes" / slug / "out"
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    row = row_of(r, slug)
    if row.get("youtube_id"):
        return row
    yt = youtube.service()
    from core import ytguard
    try:
        ytguard.check_channel(yt, os.environ.get("YT_CHANNEL_ID") or CFG.get("youtube_channel_id"))     # this channel's token
    except ytguard.Doubt as e:
        raise youtube.Doubt(str(e))
    known = [x["youtube_id"] for x in r if x.get("youtube_id")]
    videos = youtube.all_uploads(yt, known)               # raises Doubt: no upload
    same = youtube.find_existing(videos, slug, meta["title"])
    if same:
        log.warning("%s is already on the channel as %s; not uploading again", slug, same["id"])
        row.update({"youtube_id": same["id"], "title": same["title"],
                    "state": "scheduled" if same["publish_at"] else "published",
                    **({"publish_at": same["publish_at"]} if same["publish_at"] else {})})
        save(r)
        persist(f"state: {slug} is already on YouTube ({same['id']})")
        return row
    ahead = CFG["schedule"]["ahead"]
    queued = sum(1 for x in r if x.get("state") == "scheduled" and (x.get("publish_at") or "") > _now_z())
    if os.environ.get("AS_RESERVE") == "1" or queued >= ahead:
        # the next two slots are taken: this one is the emergency reserve - private, no date; the
        # watchdog gives it a slot when one is less than 24 h away and empty
        state, when = "reserve", None
    else:
        state, when = "scheduled", _slot(videos, r)
    if os.environ.get("DRY_RUN"):
        print(f"DRY RUN {slug}: would upload '{meta['title']}' as {state}, publish {when}; the channel has "
              f"{len(videos)} videos, none of them this episode")
        return row
    desc = meta["description"].rstrip() + "\n\n" + youtube.REF.format(slug=slug)
    vid = youtube.upload(out / "video.mp4", meta["title"], desc, meta["tags"], when, yt=yt,
                         synthetic=bool(meta.get("contains_synthetic_media")))
    row.update({"youtube_id": vid, "state": state, "slug": slug,
                "title": meta["title"], **({"publish_at": when.strftime("%Y-%m-%dT%H:%M:%SZ")} if when else {})})
    save(r)                                   # the id is kept before anything else can fail
    try:
        from pipeline import material_de
        used = json.loads((out / "sources.json").read_text(encoding="utf-8"))
        material_de.mark_used(slug, [f["id"] for f in used.get("films", [])], [p["file"] for p in used.get("photos", [])])
    except Exception as e:                                       # noqa: BLE001
        log.warning("usage of %s not marked: %s", slug, e)
    persist(f"state: {slug} uploaded as {vid}")
    caps = {k: out / f"subtitles_{k}.srt" for k in ("de", "en") if (out / f"subtitles_{k}.srt").exists()}
    row["captions"] = youtube.set_captions(vid, caps, yt=yt)
    save(r)
    persist(f"state: {slug} captions {row['captions']}")
    try:
        youtube.set_thumbnail(vid, out / "thumbnail.jpg")
    except Exception as e:                                           # noqa: BLE001
        row["thumbnail"] = f"failed: {str(e)[:120]}"
        save(r)
        persist(f"state: {slug} thumbnail failed")
    return row


def _doubt(slug, r, e):
    """Not sure the channel was read in full: nothing is uploaded, the episode stays built, one mail."""
    row = row_of(r, slug)
    first = not row.get("doubt_mailed")
    row.update({"state": "built", "doubt": str(e)[:300], "doubt_mailed": True})
    save(r)
    persist(f"state: {slug} built, upload held (not sure about the channel)")
    log.error("upload of %s cancelled: %s", slug, e)
    if first:
        notify(f"Upload of {slug} cancelled - not sure the channel was read in full",
               f"{e}\nThe episode is built and waits; the watchdog tries the upload again.")


def record(slug):
    r = rows()
    qa = json.loads((ROOT / "episodes" / slug / "out" / "qa.json").read_text(encoding="utf-8"))
    row = row_of(r, slug)
    if row.get("youtube_id") or row.get("state") in ("built", "scheduled", "published", "reserve"):
        # 13.11: already on YouTube - a later build of the same topic changes nothing there
        log.info("%s is already %s (%s); this build is not recorded", slug, row.get("state"), row.get("youtube_id"))
        return 0
    if not qa.get("passed"):
        row["state"] = "qa-failed"
        row["qa_failed"] = [k for k, v in qa.items() if isinstance(v, dict) and v.get("pass") is False
                            and v.get("blocking", True)]
        save(r)
        persist(f"state: {slug} failed QA")
        log.error("%s failed QA: %s", slug, row["qa_failed"])
        return 1
    row.setdefault("state", "built")
    row["slug"] = slug
    save(r)
    persist(f"state: {slug} built")               # from here no later build of the topic renders again
    if youtube.has_token():
        try:
            _upload(slug, r)
        except youtube.Doubt as e:
            _doubt(slug, r, e)
    else:
        log.info("%s built and buffered; no YouTube token yet", slug)
    return 0


def upload():
    r = rows()
    for row in [x for x in r if x.get("state") == "built" and not x.get("youtube_id")]:
        try:
            _upload(row["slug"], r)
        except youtube.Doubt as e:
            _doubt(row["slug"], r, e)
    return 0


def dry(slug=""):
    """A dry run: reads the channel in full and says what an upload would do. Nothing is sent or saved."""
    os.environ["DRY_RUN"] = "1"
    r = rows()
    yt = youtube.service()
    from core import ytguard
    ch = ytguard.check_channel(yt, os.environ.get("YT_CHANNEL_ID") or CFG.get("youtube_channel_id"))
    print(f"the token is the channel {ch['id']} ({ch['snippet']['title']}), as configured")
    known = [x["youtube_id"] for x in r if x.get("youtube_id")]
    videos = youtube.all_uploads(yt, known)
    print(f"the channel: {len(videos)} videos read in full; the state knows {len(known)} of them, all present")
    taken = [x["publish_at"] for x in r if x.get("publish_at")] + youtube.channel_dates(videos)
    print("days held:", sorted({t[:10] for t in taken}))
    print("the next free slot:", youtube.next_slot(taken))
    for x in r:
        if x.get("title") or x.get("youtube_id"):
            same = youtube.find_existing(videos, x["slug"], x.get("title") or "")
            print(f"  {x['slug']}: state {x.get('state')}, id {x.get('youtube_id')}, "
                  f"found on the channel: {same['id'] if same else None}")
    if slug:
        title = next((x.get("title") for x in r if x["slug"] == slug), "") or "-"
        same = youtube.find_existing(videos, slug, title)
        print(f"an upload of {slug} would be:", f"SKIPPED (already {same['id']})" if same else "sent")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    sys.exit({"record": lambda: record(sys.argv[2]), "upload": upload,
              "dry": lambda: dry(*sys.argv[2:3])}[cmd]())
