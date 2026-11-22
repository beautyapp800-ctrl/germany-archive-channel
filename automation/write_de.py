"""Script and picture list of one queued topic, written ahead of its build.

    python automation/write_de.py <slug>      # episodes/<slug>/script.json + material.json
    python automation/write_de.py --next      # the next queued topic without a script

Exit codes: 0 written; 3 skipped (not enough free pictures: the topic is marked skipped in the queue and the
next one follows, owner 22.11); 5 the script failed (counted; a second failure skips the topic); 4 no text provider could answer today (state/quota_hold.json, nothing is
retried before the Gemini/Groq day turns); 1 any other failure.
No pictures, no script: the material is searched first, so no LLM tokens go to a topic that cannot be shown.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from automation import quota_hold, topic_guard  # noqa: E402
from core.logger import get_logger  # noqa: E402
from pipeline import find_material_de, material_de, scriptwriter_de, sources  # noqa: E402

log = get_logger("write-de")
QUEUE = ROOT / "topics" / "queue.json"
MIN_FREE_PHOTOS, MIN_FILMS = 140, 3          # fresh free photos / usable films (one of the two is enough, see enough())


def queue():
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def mark(slug, **kw):
    q = queue()
    for t in q["topics"]:
        if t["slug"] == slug:
            t.update(kw)
    QUEUE.write_text(json.dumps(q, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def enough(mat):
    """The picture list can fill about 13 minutes of 2.4-4 s shots, none of them used within 4 weeks."""
    films, photos = len(mat["films"]), len(mat["photos"])
    return (films >= MIN_FILMS and films * 25 + photos >= 160) or photos >= 300


def next_slug():
    for t in queue()["topics"]:
        if t.get("status", "queued") != "queued" or (ROOT / "episodes" / t["slug"] / "script.json").exists():
            continue
        why = topic_guard.blocked(t["slug"])
        if why:
            log.info("%s: %s", t["slug"], why)
            continue
        return t["slug"]
    return ""


def main(slug):
    topic = next(t for t in queue()["topics"] if t["slug"] == slug)
    if quota_hold.active():
        log.info("the text providers' day is held; %s waits", slug)
        return 4
    # 1. the pictures first
    mat = find_material_de.find(topic)
    checked = material_de.check(slug)
    fresh = {"films": checked["films"], "photos": checked["photos"]}
    log.info("%s: %d films and %d free photos usable", slug, len(fresh["films"]), len(fresh["photos"]))
    if not enough({"films": fresh["films"], "photos": fresh["photos"]}):
        mark(slug, status="skipped", skipped_why=f"not enough free pictures: {len(fresh['films'])} films, "
                                                  f"{len(fresh['photos'])} photos")
        log.warning("%s skipped: not enough pictures", slug)
        return 3
    (ROOT / "episodes" / slug / "material.json").write_text(json.dumps(
        {"films": [f["id"] for f in fresh["films"]], "photos": [p["file"] for p in fresh["photos"]]},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    # 2. the script
    found = sources.gather(topic["wikipedia"], "de")
    try:
        script = scriptwriter_de.write(topic, found)
    except Exception as e:                                           # noqa: BLE001
        if quota_hold.spent(e):
            h = quota_hold.set_(slug)
            log.warning("TEXT_DAY_SPENT: no provider can write %s today (%s); builds wait until %s", slug, str(e)[:160],
                        h["until"])
            return 4
        log.error("%s: script not written: %s", slug, e)
        fails = int(topic.get("script_fails", 0)) + 1
        if fails >= 2:
            mark(slug, status="skipped", script_fails=fails, skipped_why=f"its script failed {fails} times: {str(e)[:120]}")
        else:
            mark(slug, script_fails=fails)
        return 5
    (ROOT / "episodes" / slug / "script.json").write_text(json.dumps(script, indent=1, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
    mark(slug, status="ready")
    log.info("%s: script written (%d words)", slug, scriptwriter_de.words(script))
    return 0


if __name__ == "__main__":
    arg = sys.argv[1]
    slug = next_slug() if arg == "--next" else arg
    if not slug:
        print("no topic to write")
        sys.exit(0)
    sys.exit(main(slug))
