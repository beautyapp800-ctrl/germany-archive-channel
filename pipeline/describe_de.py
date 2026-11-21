"""YouTube title, description and tags (owner 21.11).

Description: German, 2-3 sentences, chapters, sources and authors as plain text WITHOUT
https:// (a new channel has no advanced features, links would be cut), no < or >, at most
5000 characters, 3-5 hashtags, and the marker "[ref: germany/<slug>]" the upload guard looks for.
Title: German, at most 70 characters.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))


def _mmss(t):
    t = int(max(0, t))
    return f"{t // 60}:{t % 60:02d}" if t < 3600 else f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def chapters(timeline):
    out, seen = [], set()
    for ln in timeline:
        if ln["chapter"] in seen:
            continue
        seen.add(ln["chapter"])
        t = 0 if not out else max(0, ln["start"] - 0.6)
        out.append(f"{_mmss(t)} {ln['chapter_title']}")
    return out


def clean(text):
    text = text.replace("https://", "").replace("http://", "").replace("<", "‹").replace(">", "›")
    return text


def _author(p):
    a = (p.get("author") or "").strip()
    if not a or a.lower().startswith("unknown"):
        a = (p.get("credit") or "").strip()
    return a[:80] or "unbekannt"


def description(script, timeline, used_films, used_photos, slug):
    intro = (f"{script['hook_question']} Im Sommer 1948 sperrte die Sowjetunion alle Land- und Wasserwege nach West-Berlin – "
             "und die Westalliierten antworteten mit der größten Luftbrücke der Geschichte. "
             "Mit echten Archivfilmen und Fotos, konkreten Zahlen und Quellen.")
    parts = [intro, "", "KAPITEL", *chapters(timeline), "", "QUELLEN"]
    parts += [f"- {s['what']}: {s['where']}" for s in script["sources"]]
    parts += ["", "ARCHIVFILME (gemeinfrei; jede Lizenz an der Quelle geprüft)"]
    for f in used_films:
        who = f" ({f['creator']})" if f.get("creator") else ""
        parts.append(f"- {f['title']}{who}, {f.get('date') or 'o. J.'} – {f['page']} – {f.get('basis_de', 'gemeinfrei')}")
    parts += ["", "FOTOS"]
    by = [p for p in used_photos if p["licence"].lower().startswith("cc by")]
    rest = [p for p in used_photos if p not in by]
    groups = Counter(f"{_author(p)} ({p['licence']})" for p in rest)
    parts += [f"- {k}: {v} Foto{'s' if v > 1 else ''}" for k, v in groups.most_common()]
    for p in by:
        parts.append(f"- {p['file'].replace('File:', '')} – {_author(p)} – {p['licence']} – {p['page']}")
    parts += ["Fotos über Wikimedia Commons; die Liste aller Bilder mit Lizenz steht im Projekt-Repository.", "",
              "MUSIK (CC0)"]
    parts += [f"- {t['title']} – {t['creator']} – {t['page']}" for t in CFG["music"]["tracks"]]
    parts += ["", "SO ENTSTEHT DAS VIDEO",
              "Die Sprecherstimme ist synthetisch (Piper). Alle Bilder sind echte Archivaufnahmen; restauriert wird nur "
              "klassisch (Entrauschen, Stabilisieren, leichtes Hochskalieren), ohne generative KI. Schwarz-Weiß bleibt "
              "Schwarz-Weiß.", "", "#Luftbrücke #Berlin #Nachkriegszeit #Geschichte #Rosinenbomber", "",
              f"[ref: {CFG['ref']}/{slug}]"]
    text = clean("\n".join(parts))
    while len(text.encode("utf-8")) > 4900:
        # too long: the photo lines with one picture go first, never the films or sources
        ones = [i for i, l in enumerate(parts) if l.startswith("- ") and l.endswith(": 1 Foto")]
        if not ones:
            break
        parts.pop(ones[-1])
        text = clean("\n".join(parts))
    return text


def problems(title, text):
    bad = []
    if len(title) > 70:
        bad.append(f"title {len(title)} chars")
    if "http" in text or "<" in text or ">" in text:
        bad.append("link or angle bracket in the description")
    if len(text.encode("utf-8")) > 5000:
        bad.append("description over 5000 bytes")
    if "[ref: " not in text:
        bad.append("no [ref: ...] marker")
    tags = [w for w in text.split() if w.startswith("#")]
    if not 3 <= len(tags) <= 5:
        bad.append(f"{len(tags)} hashtags")
    return bad
