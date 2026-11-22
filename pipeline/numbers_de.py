"""German number words back to digits for the subtitles.

The script spells numbers out so Piper reads them right ("eintausenddreihundertachtundneunzig");
on screen that is unreadable (pilot 22.11), so the German subtitles show digits:
  eintausenddreihundertachtundneunzig -> 1.398     neunzehnhundertneunundvierzig -> 1949
  sechzehnter April -> 16. April                   zwölf -> 12 (one to twelve stay words)
"""
import re

UNITS = {"null": 0, "ein": 1, "eins": 1, "eine": 1, "einen": 1, "einem": 1, "einer": 1, "zwei": 2, "drei": 3,
         "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9}
TEENS = {"zehn": 10, "elf": 11, "zwölf": 12, "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15, "sechzehn": 16,
         "siebzehn": 17, "achtzehn": 18, "neunzehn": 19}
TENS = {"zwanzig": 20, "dreißig": 30, "vierzig": 40, "fünfzig": 50, "sechzig": 60, "siebzig": 70, "achtzig": 80,
        "neunzig": 90}
SMALL_WORDS = 12          # "drei Tage", "zwölf Monate" read better as words
MONTHS = "Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
ORD_ENDINGS = ("sten", "ster", "stes", "ste", "ten", "ter", "tes", "te", "tem")


def _below_100(w):
    """(value, rest) for the longest number below 100 at the start of w, or (None, w)."""
    for t, v in sorted(TEENS.items(), key=lambda kv: -len(kv[0])):
        if w.startswith(t):
            return v, w[len(t):]
    for t, v in TENS.items():
        if w.startswith(t):
            return v, w[len(t):]
    for u, uv in sorted(UNITS.items(), key=lambda kv: -len(kv[0])):
        if w.startswith(u + "und"):
            for t, tv in TENS.items():
                if w[len(u) + 3:].startswith(t):
                    return uv + tv, w[len(u) + 3 + len(t):]
    for u, uv in sorted(UNITS.items(), key=lambda kv: -len(kv[0])):
        if w.startswith(u):
            return uv, w[len(u):]
    return None, w


def _below_1000(w):
    v, rest = _below_100(w)
    if rest.startswith("hundert"):
        rest = rest[7:]
        v = (v or 1) * 100
        more, rest2 = _below_100(rest)
        if more is not None:
            v, rest = v + more, rest2
    return v, rest


def parse(word):
    """(value, year_style, rest) for a whole number word, or None."""
    w = word.lower()
    if w in UNITS and w not in ("ein", "eins", "null"):
        return None          # "eine Stadt" is an article, not a number
    year = bool(re.match(r"(neunzehn|achtzehn|zwanzig)hundert", w))
    v, rest = _below_1000(w)
    if v is None and w.startswith("tausend"):
        v, rest = 1, w
    if rest.startswith("tausend"):
        rest = rest[7:]
        v = (v or 1) * 1000
        more, rest2 = _below_1000(rest)
        if more is not None:
            v, rest = v + more, rest2
    if v is None:
        return None
    return v, year, rest


def _fmt(v, year):
    return str(v) if year else f"{v:,}".replace(",", ".")


def _word(m):
    word = m.group(0)
    p = parse(word)
    if not p:
        return word
    v, year, rest = p
    if rest == "":
        return word if v <= SMALL_WORDS and not year else _fmt(v, year)
    if rest in ORD_ENDINGS and v > 0:
        after = m.string[m.end():m.end() + 12]
        if v > SMALL_WORDS or re.match(r"\s+(" + MONTHS + ")", after):
            return f"{v}."
        return word      # "im zweiten Versuch" stays a word, "6. September" is a date
    return word          # a word that only starts like a number ("achtung", "elfenbein")


def to_digits(text):
    return re.sub(r"[A-Za-zÄÖÜäöüß]+", _word, text)
