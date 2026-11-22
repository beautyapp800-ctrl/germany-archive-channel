"""Smoke test for "Als Oma jung war": the chain on tiny inputs, no key of the text models needed.

Run by .github/workflows/smoke.yml on every push to dev; only a passing run moves dev to main.
  1. every module compiles
  2. numbers, subtitles, description, slot logic
  3. a synthetic photo through the Ken Burns clip, the overlay and the QA frame checks
     (bars, coloured edges, blurred panels must FAIL; a clean picture must pass)
  4. licences: a US-Army film passes, a World-in-Film number and a forbidden source are refused
  5. with the channel token: the channel is read in full (read-only) and is the configured one
"""
import compileall
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONUTF8", "1")
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" - {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def compiles():
    ok = all(compileall.compile_dir(str(ROOT / d), quiet=1) for d in ("core", "pipeline", "automation", "scripts"))
    check("all modules compile", ok)


def text_tools():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from pipeline import describe_de, numbers_de, youtube
    check("number words", numbers_de.to_digits("eintausenddreihundertachtundneunzig Flugzeuge") == "1.398 Flugzeuge")
    check("year words", numbers_de.to_digits("im Jahr neunzehnhundertneunundvierzig") == "im Jahr 1949")
    check("date ordinals", numbers_de.to_digits("am sechzehnten April") == "am 16. April")
    check("small words stay", numbers_de.to_digits("drei Tage") == "drei Tage")
    s = youtube.next_slot(now=datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc))
    loc = s.astimezone(ZoneInfo("Europe/Berlin"))
    check("slot = Sunday 17:00 Berlin", (loc.weekday(), loc.hour, loc.minute) == (6, 17, 0), str(loc))
    taken = [s.strftime("%Y-%m-%dT%H:%M:%SZ")]
    s2 = youtube.next_slot(taken, now=datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc))
    check("a held slot is skipped", (s2 - s).days == 7)
    script = json.loads((ROOT / "episodes" / "luftbruecke" / "script.json").read_text(encoding="utf-8"))
    tl = [{"chapter": i, "chapter_title": c["title"], "start": 60.0 * i, "end": 60.0 * i + 50, "text": "x"}
          for i, c in enumerate(script["chapters"])]
    desc = describe_de.description(script, tl, [], [], "smoke")
    check("description has the marker", "[ref: germany/smoke]" in desc)
    check("description problems", describe_de.problems(script["title"], desc) == [],
          str(describe_de.problems(script["title"], desc)))


def picture_chain():
    import numpy as np
    from PIL import Image

    from pipeline import frames_de, qa_de, render_de
    tmp = Path(tempfile.mkdtemp())
    rng = np.random.default_rng(1)
    base = rng.integers(60, 200, (360, 640), dtype=np.uint8)
    base = np.clip(np.cumsum(base, 0) % 200 + 30, 0, 255).astype(np.uint8)
    Image.fromarray(base).convert("RGB").save(tmp / "p.jpg")
    clip = render_de.photo_clip(tmp / "p.jpg", 1.0, tmp / "c.mp4", seed=3)
    check("photo clip renders", Path(clip).exists() and Path(clip).stat().st_size > 1000)
    shot = {"start": 0, "end": 1.0, "year": 1948, "tag": "TEST", "chapter_title": "Kapitel"}
    out = render_de.finish_shot(clip, shot, tmp / "s.mp4", tmp)
    fr, sat = qa_de._frames(out)
    check("clean frames pass QA", not any(qa_de.frame_problem(f) or qa_de.coloured_edge(c) for f, c in zip(fr, sat)))
    g = fr[0].copy()
    bars = g.copy()
    bars[:30] = 0
    bars[-30:] = 0
    check("letterbox bars fail", qa_de.frame_problem(bars) == "letterbox bars")
    pil = g.copy()
    pil[:, :40] = 0
    pil[:, -40:] = 0
    check("pillarbox bars fail", qa_de.frame_problem(pil) == "pillarbox bars")
    rgb = np.stack([g] * 3, -1)
    rgb[:, :12] = (220, 60, 40)
    sat2 = rgb.max(2) - rgb.min(2)
    check("coloured edge on b/w fails", bool(qa_de.coloured_edge(sat2)))
    dark = Image.fromarray((g * 0.12).astype(np.uint8)).convert("RGB")
    check("night frame refused", frames_de.verdict(dark) == "too dark")


def licences():
    from pipeline import material_de
    f = material_de.film("ADC-7366")
    check("US Army film accepted", f["ok"] and "federal" in f.get("basis", ""), str(f.get("why")))
    check("World in Film range refused", not material_de.film("111-adc-10124")["ok"])
    check("forbidden word matches", bool(material_de.FORBIDDEN.search("Welt im Film 1952")))
    check("a harmless word does not", not material_de.FORBIDDEN.search("map of the capital"))
    check("Nazi title refused", bool(material_de.NAZI.search("Berlin 1938 parade")))


def channel():
    if not os.environ.get("YT_TOKEN_JSON"):
        print("SKIP channel read (no token in this run)")
        return
    from core import ytguard
    from pipeline import youtube
    yt = youtube.service()
    ch = ytguard.check_channel(yt, os.environ.get("YT_CHANNEL_ID"))
    check("token is the configured channel", True)
    vids = youtube.all_uploads(yt)
    print(f"channel {ch['snippet']['title']}: {len(vids)} videos read in full")


if __name__ == "__main__":
    for step in (compiles, text_tools, picture_chain, licences, channel):
        try:
            step()
        except Exception as e:                                       # noqa: BLE001
            check(step.__name__, False, f"{type(e).__name__}: {e}")
    print(f"{len(FAILS)} failed" if FAILS else "smoke passed")
    sys.exit(1 if FAILS else 0)
