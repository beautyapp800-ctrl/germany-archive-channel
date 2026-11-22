"""The script of one episode, written from de.wikipedia articles and checked against them.

    script = scriptwriter_de.write(topic, sources)       # the same JSON as episodes/luftbruecke/script.json

Stages (every LLM call through core.llm: Groq first, Gemini as fallback):
  1. outline   title (<= 70 characters), hook question, intro, hashtags, tags, cover words and 12-14 chapters,
               each with the facts (number, date, name) it must carry - taken from the articles only
  2. chapters  5-9 lines each: "text" (German, every number spelled out for the voice), "en" (English with
               digits, for the subtitles), "look" (what the camera sees, in English, for the picture match),
               "tag" (a short number sticker on the line that carries the chapter's key figure)
  3. checks    no digits and no Nazi-period words in the spoken text, no line that cannot be pictured,
               every number of an English line found in the articles (a line with an unsupported number is
               dropped), total length for 12-16 minutes (the chapters are extended when short)
Nothing here needs the pictures; episodes/<slug>/material.json is found separately.
"""
import json
import re

from core import llm
from core.logger import get_logger
from pipeline import numbers_de

log = get_logger("scriptwriter-de")
WORDS_MIN, WORDS_MAX = 1780, 2250          # 12.0 - 16.0 minutes at the voice's pace (pilot: 1810 words = 12.75 min)
NAZI = re.compile(r"nazi|hitler|swastika|hakenkreuz|nsdap|wehrmacht|\bSS\b|gestapo|f[üu]hrer|konzentrationslager|"
                  r"holocaust|reichsparteitag", re.I)
SYSTEM = ("Du schreibst Sprechertexte für deutsche Geschichtsdokumentationen auf YouTube (Kanal 'Als Oma jung war', "
          "Deutschland 1945-1970). Stil: klar, lebendig, konkret, kurze Sätze, kein Pathos, keine Floskeln. "
          "Jede Aussage muss aus den gelieferten Quellen stammen; erfinde nichts, runde keine Zahlen um. "
          "Die NS-Zeit und ihre Symbole kommen nicht vor.")
EXAMPLE = [
    {"text": "Ostersonntag, sechzehnter April neunzehnhundertneunundvierzig.",
     "en": "Easter Sunday, 16 April 1949.", "look": "a four-engine cargo plane landing at an airfield in Berlin"},
    {"text": "In vierundzwanzig Stunden landen in West-Berlin eintausenddreihundertachtundneunzig Flugzeuge.",
     "en": "In 24 hours, 1,398 aircraft land in West Berlin.",
     "look": "many cargo planes parked in a row on an airfield", "tag": "1.398 FLÜGE"}]


def _src(sources, limit=36000):
    out, left = [], limit
    for s in sources:
        part = f"### {s['title']}\n{s['text'][:max(2000, left // max(1, len(sources)))]}"
        out.append(part)
        left -= len(part)
    return "\n\n".join(out)


def outline(topic, sources):
    p = f"""Thema: {topic['name']} (Jahr {topic['year_label']}, Ort: {topic['place']}).

QUELLEN (de.wikipedia):
{_src(sources)}

Plane die Folge. Antworte NUR mit JSON:
{{"title": "deutscher YouTube-Titel, höchstens 68 Zeichen, so wie Leute danach suchen (Jahreszahl, konkretes Thema, Frage oder Zahl)",
 "hook_question": "eine Frage, die in den ersten Sekunden neugierig macht",
 "intro": "zwei Sätze für die Videobeschreibung, was die Folge zeigt (ohne Frage am Anfang)",
 "hashtags": ["#...", "3 bis 5 Stück"],
 "tags": ["8 Suchbegriffe"],
 "cover": {{"hero": "english: the main visible subject of the cover, one short phrase a camera could film",
           "hooks": ["drei Hook-Texte, je 2-4 Wörter, GROSSBUCHSTABEN", "...", "..."],
           "tag": "kurzer Zahlen-Sticker, z.B. '1.398 FLÜGE' (aus den Quellen)",
           "stamp": "ein Wort mit Ausrufe-/Fragezeichen: ECHT? oder UNGLAUBLICH oder VERBOTEN?"}},
 "chapters": [{{"title": "Kapiteltitel, höchstens 4 Wörter", "facts": ["3-6 konkrete Fakten dieses Kapitels mit Zahl/Datum/Namen, wörtlich aus den Quellen"]}}]}}
Regeln: 12 bis 14 Kapitel; Kapitel 1 ist der Hook (stärkste Zahl oder Szene, gleich zu Beginn); die Reihenfolge erzählt eine Geschichte
(Ausgangslage, Wendepunkt, Alltag mit Preisen/Löhnen/Zahlen, Folgen, Fazit); jedes Kapitel hat mindestens drei Fakten; die Folge enthält
konkrete Zahlen (Preise in DM, Löhne, Mengen) nur, wenn sie in den Quellen stehen; keine NS-Zeit."""
    o = llm.complete_json(p, SYSTEM, max_tokens=5000, temperature=0.5)
    ch = o.get("chapters") or []
    if not 10 <= len(ch) <= 16:
        raise llm.LLMError(f"outline with {len(ch)} chapters")
    return o


def chapter(topic, sources, title, facts, first=False, last=False, more=0, earlier=()):
    role = ("Dies ist das ERSTE Kapitel: gleich im ersten Satz die stärkste Zahl oder Szene, Hook in den ersten 15-30 Sekunden. "
            if first else "")
    role += ("Dies ist das LETZTE Kapitel: Fazit, was bleibt, ein Satz zu den Quellen. " if last else "")
    p = f"""Thema der Folge: {topic['name']}. Kapitel: "{title}".
{role}
{('BEREITS GESAGT in anderen Kapiteln (nichts davon wiederholen, auch nicht anders formuliert):' + chr(10) + chr(10).join('- ' + e for e in list(earlier)[-70:]) + chr(10)) if earlier else ''}
FAKTEN (nur diese und die Quellen unten verwenden):
{chr(10).join('- ' + f for f in facts)}

QUELLEN:
{_src(sources, 14000)}

Schreibe {'mindestens 11, höchstens 14' if more else 'mindestens 9, höchstens 12'} Sprecherzeilen von je 12 bis 26 Wörtern (zusammen {'230 bis 300' if more else '170 bis 240'} Wörter, nicht weniger). Erzähle ausführlich: Ausgangslage, Zahl, Folge, Beispiel aus dem Alltag, solange es in den Quellen steht. Antworte NUR mit JSON: {{"lines": [...]}}
Jede Zeile: {{"text": "...", "en": "...", "look": "...", "tag": "..."(optional)}}
- text: gesprochenes Deutsch, höchstens 30 Wörter; ALLE Zahlen als Wörter ausschreiben, wie ein Sprecher sie liest
  (neunzehnhundertachtundvierzig, eintausenddreihundertachtundneunzig, sechzehnter April, vierzig D-Mark, zwölf Prozent)
- en: englische Übersetzung mit Ziffern (1,398; 16 April 1949; 40 DM)
- look: english, what a camera could have filmed or photographed for this line (people, places, objects; no abstract ideas, no text, no names)
- tag: nur bei der Zeile mit der Schlüsselzahl des Kapitels, höchstens 14 Zeichen, z.B. "40 D-MARK" (sonst weglassen)
Beispiel: {json.dumps(EXAMPLE, ensure_ascii=False)}
Keine Zeile ohne Bezug zu den Fakten; keine NS-Zeit; keine Wertungen ohne Beleg."""
    o = llm.complete_json(p, SYSTEM, max_tokens=3500, temperature=0.55)
    return o["lines"] if isinstance(o, dict) else o


def _nums(en):
    """The numbers of an English line, as digit strings without separators."""
    return {re.sub(r"[.,\s]", "", m) for m in re.findall(r"\d[\d.,]*\d|\d", en)}


def _supported(en, corpus):
    for n in _nums(en):
        if len(n) <= 2 and int(n) <= 31:       # small counts, days of a month
            continue
        if n not in corpus:
            return False
    return True


def _tok(en):
    return {w for w in re.findall(r"[a-zäöüß]{4,}", en.lower())}


def _dupe(en, earlier):
    """The line says what an earlier line already said (same words, or the same figure in similar words)."""
    a, nums = _tok(en), _nums(en)
    for e in earlier:
        b = _tok(e)
        if not a or not b:
            continue
        j = len(a & b) / len(a | b)
        if j >= 0.45 or (j >= 0.25 and any(len(n) > 2 or int(n) > 31 for n in nums & _nums(e))):
            return True
    return False


def clean_lines(lines, corpus, earlier=()):
    """The valid lines of a chapter: digits spelled out, no Nazi words, numbers backed by the articles."""
    out, dropped = [], []
    for ln in lines:
        text, en, look = (ln.get("text") or "").strip(), (ln.get("en") or "").strip(), (ln.get("look") or "").strip()
        if not text or not en or not look:
            dropped.append(("incomplete", text[:50]))
            continue
        if re.search(r"\d", text):
            text = numbers_de.to_words(text)
        if NAZI.search(text) or NAZI.search(en) or NAZI.search(look):
            dropped.append(("nazi period", text[:50]))
            continue
        if not _supported(en, corpus):
            dropped.append(("number not in the articles", en[:60]))
            continue
        if len(text.split()) > 40:
            dropped.append(("too long", text[:50]))
            continue
        if _dupe(en, list(earlier) + [r["en"] for r in out]):
            dropped.append(("repeats an earlier line", en[:60]))
            continue
        row = {"text": text, "en": en, "look": look}
        if ln.get("tag"):
            row["tag"] = str(ln["tag"]).upper()[:14]
        out.append(row)
    return out, dropped


def _w(lines):
    return sum(len(ln["text"].split()) for ln in lines)


def words(script):
    return sum(len(ln["text"].split()) for c in script["chapters"] for ln in c["lines"])


def write(topic, sources):
    corpus = re.sub(r"[.,\s]", "", " ".join(s["text"] for s in sources))
    # numbers as they stand in the articles, with and without the German thousands dot
    corpus_nums = set(re.sub(r"[.,\s]", "", m) for s in sources for m in re.findall(r"\d[\d.,]*\d|\d", s["text"]))
    o = outline(topic, sources)
    chapters = []
    for i, c in enumerate(o["chapters"]):
        best, dropped = [], []
        for attempt in range(3):
            earlier = [ln["en"] for ch in chapters for ln in ch["lines"]]
            raw = chapter(topic, sources, c["title"], c.get("facts") or [], first=i == 0, last=i == len(o["chapters"]) - 1,
                          more=1 if attempt else 0, earlier=earlier)
            lines, dropped = clean_lines(raw, corpus_nums, earlier)
            if _w(lines) > _w(best):
                best = lines
            if _w(best) >= 150:
                break
            log.info("chapter %d '%s': %d words (%s); again", i + 1, c["title"], _w(best), dropped[:3])
        lines = best
        if len(lines) < 3:
            raise llm.LLMError(f"chapter '{c['title']}' has {len(lines)} usable lines")
        chapters.append({"title": c["title"], "facts": c.get("facts") or [], "lines": lines})
        log.info("chapter %d '%s': %d lines, %d dropped", i + 1, c["title"], len(lines), len(dropped))
    script = {"slug": topic["slug"], "title": o["title"][:70], "year_label": str(topic["year_label"]), "place": topic["place"],
              "hook_question": o["hook_question"], "intro": o["intro"],
              "hashtags": o["hashtags"][:5], "tags": o["tags"][:12], "cover": o["cover"],
              "sources": [{"what": s["title"], "where": "de.wikipedia.org/wiki/" + s["title"].replace(" ", "_"),
                           "revision": s.get("revision")} for s in sources],
              "chapters": chapters}
    # too short: the chapters with the fewest words are written again, longer
    for _ in range(4):
        if words(script) >= WORDS_MIN:
            break
        short = [k for k in range(len(chapters)) if _w(chapters[k]["lines"]) < 150][:8] or             sorted(range(len(chapters)), key=lambda k: _w(chapters[k]["lines"]))[:4]
        for k in short:
            c = chapters[k]
            others = [ln["en"] for j, ch in enumerate(chapters) if j != k for ln in ch["lines"]]
            raw = chapter(topic, sources, c["title"], c["facts"], first=k == 0, last=k == len(chapters) - 1, more=1,
                          earlier=others)
            lines, _ = clean_lines(raw, corpus_nums, others)
            if _w(lines) > _w(c["lines"]):
                c["lines"] = lines
        log.info("after extending: %d words", words(script))
    # too long: whole lines off the end of the longest chapters (never the first or last)
    while words(script) > WORDS_MAX:
        mid = sorted(range(1, len(chapters) - 1), key=lambda k: -len(chapters[k]["lines"]))
        if len(chapters[mid[0]]["lines"]) <= 4:
            break
        chapters[mid[0]]["lines"].pop()
    for c in chapters:
        c.pop("facts", None)
    log.info("script %s: %d chapters, %d words", topic["slug"], len(chapters), words(script))
    problems = check(script)
    if problems:
        raise llm.LLMError("script problems: " + "; ".join(problems))
    return script


def check(script):
    out = []
    if len(script["title"]) > 70:
        out.append(f"title {len(script['title'])} characters")
    if not 3 <= len(script["hashtags"]) <= 5:
        out.append("hashtags")
    n = words(script)
    if not 1600 <= n <= WORDS_MAX + 100:          # 1600 words = 12.0 min at the slowest retime (length_scale 1.10)
        out.append(f"{n} words")
    if len(script["cover"].get("hooks", [])) < 3:
        out.append("cover hooks")
    if len(script["chapters"]) < 10:
        out.append("chapters")
    return out
