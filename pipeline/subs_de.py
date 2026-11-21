"""Subtitles as separate files (owner: uploaded with captions.insert, never burnt in).

German from the script's own words, timed by the narration; English from each line's "en".
A cue holds at most two rows of 42 characters; a longer line is split at a sentence or
comma boundary in proportion to its characters.
"""
import re
import textwrap

MAX_ROW, MAX_ROWS = 42, 2


def _ts(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _pieces(text):
    if len(text) <= MAX_ROW * MAX_ROWS:
        return [text]
    parts = re.split(r"(?<=[.!?:;])\s+|(?<=,)\s+", text)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > MAX_ROW * MAX_ROWS:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    final = []
    for p in out:
        while len(p) > MAX_ROW * MAX_ROWS:
            cut = p.rfind(" ", 0, MAX_ROW * MAX_ROWS)
            final.append(p[:cut])
            p = p[cut + 1:]
        final.append(p)
    return final


def srt(timeline, field="text"):
    cues = []
    for ln in timeline:
        text = ln.get(field) or ln["text"]
        parts = _pieces(text)
        total = sum(len(p) for p in parts)
        t = ln["start"]
        for p in parts:
            d = (ln["end"] - ln["start"]) * len(p) / total
            cues.append((t, t + d, "\n".join(textwrap.wrap(p, MAX_ROW))))
            t += d
    return "".join(f"{k}\n{_ts(a)} --> {_ts(b)}\n{txt}\n\n" for k, (a, b, txt) in enumerate(cues, 1))
