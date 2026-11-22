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


# ---------------------------------------------------------------- digits to words (for the voice)

_ONES = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf",
         "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn"]
_TENS = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"]
_ORD = {1: "ersten", 3: "dritten", 7: "siebten", 8: "achten"}


def _w100(n):
    if n < 20:
        return _ONES[n]
    t, u = divmod(n, 10)
    return _TENS[t] if u == 0 else ("ein" if u == 1 else _ONES[u]) + "und" + _TENS[t]


def _w1000(n):
    h, r = divmod(n, 100)
    return (("" if h == 1 else _ONES[h]) + "hundert" if h else "") + (_w100(r) if r else "")


def cardinal(n, year=False):
    """1398 -> eintausenddreihundertachtundneunzig; as a year 1949 -> neunzehnhundertneunundvierzig."""
    if n < 0:
        return "minus " + cardinal(-n)
    if year and 1100 <= n <= 1999:
        h, r = divmod(n, 100)
        return _w100(h) + "hundert" + (_w100(r) if r else "")
    if n < 1000:
        return _w1000(n) if n >= 100 else _w100(n)
    if n < 1_000_000:
        k, r = divmod(n, 1000)
        head = "eintausend" if k == 1 else (_w1000(k) if k >= 100 else _w100(k)) + "tausend"
        return head + (_w1000(r) if r >= 100 else (_w100(r) if r else ""))
    m, r = divmod(n, 1_000_000)
    head = ("eine Million" if m == 1 else f"{cardinal(m)} Millionen")
    return head + (" " + cardinal(r) if r else "")


def ordinal_dative(n):
    """16 -> sechzehnten, 3 -> dritten, 21 -> einundzwanzigsten ("am 16. April")."""
    if n in _ORD:
        return _ORD[n]
    return cardinal(n) + ("ten" if n < 20 else "sten")


def to_words(text):
    """Every digit in the text spelled out the way a speaker reads it."""
    def num(m):
        raw = m.group(0)
        if re.fullmatch(r"\d+,\d+", raw):
            a, b = raw.split(",")
            return cardinal(int(a)) + " Komma " + " ".join(cardinal(int(d)) for d in b) if len(b) == 1 else \
                cardinal(int(a)) + " Komma " + cardinal(int(b))
        n = int(raw.replace(".", ""))
        return cardinal(n, year=bool(re.fullmatch(r"1[1-9]\d\d", raw)))
    def date(m):
        o = ordinal_dative(int(m.group(1)))
        before = text[max(0, m.start() - 6):m.start()].strip().lower()
        if before.endswith("der") or before.endswith("ist"):        # nominative: "der dreizehnte August"
            o = o[:-1] if o.endswith("n") else o
        return o + " " + m.group(2)
    t = re.sub(r"(\d{1,2})\.\s+(" + MONTHS + ")", date, text)
    t = re.sub(r"(\d+)\s?%", lambda m: cardinal(int(m.group(1))) + " Prozent", t)
    t = re.sub(r"\bD-?Mark\b|\bDM\b", "D-Mark", t)
    t = re.sub(r"(?<![A-Za-z-])1 Million\b", "eine Million", t)
    t = re.sub(r"\d{1,3}(?:\.\d{3})+|\d+,\d+|\d+", num, t)
    return t
