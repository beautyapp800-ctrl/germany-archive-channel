"""The shot plan: which picture is on screen under every moment of the narration.

Rhythm (owner 21.11): constant movement, no picture longer than 4 s, the picture matches
the words. Every line is cut into equal shots of 2.4-4.0 s; a line shorter than that
shares one shot with the next.

Candidates: the shots of every checked film (scene cuts on a small proxy, pipeline/clips.shots;
a long take gives several different 4 s stretches, never the same stretch twice) and every
checked photo (each once per episode, shown as a slow move).
Matching: SigLIP on the runner's CPU scores each line's English picture description ("look")
against every candidate frame. Shots are filled in order with the best unused candidate; the
first 30 s (the hook) prefer the most vivid pictures. Frames that SigLIP reads as showing Nazi
symbols are dropped before matching (owner: banned in Germany; Gemini checks again when its key
is set, pipeline/vision.py).
"""
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageStat

from core.logger import get_logger

log = get_logger("plan")
ROOT = Path(__file__).resolve().parent.parent
EDIT = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))["edit"]
SHOT_MIN, SHOT_MAX = EDIT["shot_min_s"], EDIT["shot_max_s"]
SYMBOL_TEXTS = ["a swastika", "a flag with a swastika", "a nazi eagle emblem with a swastika", "a nazi salute"]
NEUTRAL_TEXTS = ["an old photograph", "a black and white film frame", "people in a street", "an airplane"]


def segments(timeline):
    """[(start, end, line index)] shots on the narration clock: each <= SHOT_MAX, >= SHOT_MIN where possible."""
    out = []
    carry = None
    for i, ln in enumerate(timeline):
        a = carry if carry is not None else ln["start"]
        b = timeline[i + 1]["start"] if i + 1 < len(timeline) else ln["end"] + 1.2
        d = b - a
        if d < SHOT_MIN and i + 1 < len(timeline):
            carry = a                       # too short for a shot of its own: joins the next line
            continue
        carry = None
        n = max(1, math.ceil(d / SHOT_MAX - 1e-6))
        step = d / n
        for k in range(n):
            out.append((round(a + k * step, 3), round(a + (k + 1) * step, 3), i))
    return out


def vivid(path):
    im = Image.open(path).convert("L").resize((320, 180))
    st = ImageStat.Stat(im)
    edges = ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).mean[0]
    return float(st.stddev[0] / 64 + edges / 20)


def _siglip():
    from pipeline import prefilter
    return prefilter


def score_matrix(texts, frames):
    pf = _siglip()
    pf._embed_texts(texts)
    pf._embed_images(frames)
    T = np.stack([pf._txt_emb[t].numpy() for t in texts])
    F = np.stack([pf._img_emb[str(f)].numpy() for f in frames])
    return T @ F.T


def symbol_flags(frames, margin=0.02):
    """True for frames SigLIP finds closer to a Nazi symbol than to any neutral description."""
    if not frames:
        return []
    S = score_matrix(SYMBOL_TEXTS + NEUTRAL_TEXTS, frames)
    sym, neu = S[:len(SYMBOL_TEXTS)].max(0), S[len(SYMBOL_TEXTS):].max(0)
    return [bool(s > n + margin) for s, n in zip(sym, neu)]


def prompt(look, year):
    return f"a {year} black and white photograph: {look}"


def plan(timeline, cands, year="1948", hook_s=30.0):
    """cands: [{"kind": "film"|"photo", "kf": frame path, "src": ..., "start"/"end" for films, ...}]."""
    flags = symbol_flags([c["kf"] for c in cands])
    dropped = [c for c, f in zip(cands, flags) if f]
    cands = [c for c, f in zip(cands, flags) if not f]
    for c in dropped:
        log.warning("dropped as a possible Nazi symbol: %s", c.get("id"))
    segs = segments(timeline)
    looks = [prompt(timeline[i]["look"], year) for _, _, i in segs]
    uniq = list(dict.fromkeys(looks))
    S = score_matrix(uniq, [c["kf"] for c in cands])
    row = {t: k for k, t in enumerate(uniq)}
    for c in cands:
        c["vivid"] = vivid(c["kf"])
        c["left"] = c.get("uses", 1)
    max_photo = EDIT.get("photo_share_max", 0.75)
    shots, recent, photos_used = [], [], 0
    for n, (a, b, i) in enumerate(segs):
        d = b - a
        s = S[row[looks[n]]].copy()
        best, best_v = None, -9
        for k, c in enumerate(cands):
            if c["left"] <= 0:
                continue
            if c["kind"] == "film" and (c["end"] - c["start"]) < d + 0.3:
                continue
            if c["kind"] == "photo" and photos_used >= max_photo * len(segs):
                continue
            v = s[k]
            if a < hook_s:
                v += 0.015 * c["vivid"]
            if c.get("film_id") in recent[-2:]:
                v -= 0.03                       # the same film right before: something else, if as good
            if v > best_v:
                best, best_v = k, v
        if best is None:
            raise RuntimeError(f"no picture left for the shot at {a:.1f} s")
        c = cands[best]
        c["left"] -= 1
        shot = {"start": a, "end": b, "line": i, "chapter": timeline[i]["chapter"], "score": round(float(s[best]), 4),
                "kind": c["kind"], "id": c["id"], "kf": c["kf"]}
        if c["kind"] == "film":
            # each use of a long take is a different stretch of it
            used = c.setdefault("used_at", [])
            off = c["start"] + 0.2 + len(used) * (d + 0.4)
            if off + d > c["end"]:
                off = c["start"] + 0.2
            used.append(off)
            shot.update(film_id=c["film_id"], src=c["src"], src_start=round(off, 2), year=c.get("year"))
        else:
            photos_used += 1
            shot.update(src=c["src"], year=c.get("year"), size=c.get("size"))
        recent.append(c.get("film_id") or c["id"])
        shots.append(shot)
    # mark the first shot of every line that carries a tag, and of every chapter
    seen_line, seen_ch = set(), set()
    for s in shots:
        ln = timeline[s["line"]]
        if ln.get("tag") and s["line"] not in seen_line:
            s["tag"] = ln["tag"]
        if s["chapter"] not in seen_ch and s["chapter"] > 0:
            s["chapter_title"] = ln["chapter_title"]
        seen_line.add(s["line"])
        seen_ch.add(s["chapter"])
    scores = [s["score"] for s in shots]
    log.info("plan: %d shots, %d photos, %d film stretches, median match %.3f, %d dropped for symbols",
             len(shots), photos_used, len(shots) - photos_used, float(np.median(scores)), len(dropped))
    return {"shots": shots, "dropped_symbols": [c.get("id") for c in dropped]}


def year_of(text):
    m = re.search(r"\b(194[5-9]|19[56]\d|1970)\b", str(text or ""))
    return int(m.group(1)) if m else None
