"""Checks a finished episode must pass before anything goes to YouTube.

  frames   one frame every second (owner 21.11): a black or flat band along the top/bottom or
           left/right edge (letterbox, pillarbox) or blurred side panels = the render fails
  shots    no shot longer than 4.0 s on screen (owner: constant movement)
  black    no black stretch of 3 s or more
  loudness -14 LUFS +- 1
  length   12-16 minutes
"""
import json
import re
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))
FW, FH = 320, 180


def _frames(video):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf",
                        f"fps=1,scale={FW}:{FH},format=gray", "-f", "rawvideo", "-"], capture_output=True, timeout=3600)
    a = np.frombuffer(r.stdout, np.uint8)
    return a[: len(a) // (FW * FH) * FW * FH].reshape(-1, FH, FW).astype(np.float32)


def _lap(x):
    return float(np.var(x[1:-1, 1:-1] * 4 - x[:-2, 1:-1] - x[2:, 1:-1] - x[1:-1, :-2] - x[1:-1, 2:]))


def frame_problem(f):
    """None, or what is wrong with this frame's edges."""
    bands = {"top": f[:7], "bottom": f[-7:], "left": f[:, :10], "right": f[:, -10:]}
    flat = {k: (v.std() < 5.0 and (v.mean() < 22 or v.mean() > 245)) for k, v in bands.items()}
    if flat["top"] and flat["bottom"]:
        return "letterbox bars"
    if flat["left"] and flat["right"]:
        return "pillarbox bars"
    if f.mean() > 30:
        centre = _lap(f[:, 80:240])
        sides = [_lap(f[:, :40]), _lap(f[:, -40:])]
        if centre > 120 and max(sides) < 0.06 * centre:
            return "blurred side panels"
    return None


def check(video, plan, timeline):
    res = {}
    fr = _frames(video)
    bad = [(i, p) for i, f in enumerate(fr) if (p := frame_problem(f))]
    res["frames"] = {"pass": not bad, "checked": len(fr), "bad": [{"t": i, "what": p} for i, p in bad[:30]],
                     "blocking": True}
    long_ = [s for s in plan["shots"] if s["end"] - s["start"] > CFG["edit"]["shot_max_s"] + 0.02]
    res["shots"] = {"pass": not long_, "count": len(plan["shots"]),
                    "longest_s": round(max(s["end"] - s["start"] for s in plan["shots"]), 2), "blocking": True}
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", "blackdetect=d=3:pix_th=0.08", "-an",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=3600).stderr
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)
    res["black"] = {"pass": not blacks, "stretches": blacks[:10], "blocking": True}
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "loudnorm=print_format=json", "-vn",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=3600).stderr
    m = json.loads(err[err.rfind("{"):err.rfind("}") + 1])
    res["loudness"] = {"pass": abs(float(m["input_i"]) - CFG["sound"]["target_lufs"]) <= 1.0,
                       "lufs": float(m["input_i"]), "true_peak": float(m["input_tp"]), "blocking": True}
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(video)], capture_output=True, text=True).stdout.strip() or 0)
    ep = CFG["episode"]
    res["length"] = {"pass": ep["minutes_min"] * 60 <= dur <= ep["minutes_max"] * 60, "minutes": round(dur / 60, 2),
                     "blocking": True}
    res["passed"] = all(v["pass"] for v in res.values() if isinstance(v, dict) and v.get("blocking"))
    return res
