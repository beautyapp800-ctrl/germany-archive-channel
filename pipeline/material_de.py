"""Pictures for an episode: archive films and free photos, every licence checked at the source.

Rules (owner 21./22.11):
  - only Public Domain, CC0 and CC BY (no SA, NC, ND); Bundesarchiv, Welt im Film, DEFA,
    British newsreels, March of Time, Universal Newsreel stay out;
  - US federal works (Army Signal Corps, US Air Force, USIA ...) count as public domain
    (owner's spec: "NARA, Werke der US-Regierung - PD"); the NARA catalogue's own use
    status is looked up and written next to every film;
  - Army depository copies numbered 10000 and up (111-ADC-10xxx) are left out: that range
    holds the "World in Film" newsreel issues;
  - a film or photo used by another episode in the last 28 days is not used again
    (state/usage.json); a topic without enough fresh pictures is skipped in the queue.

episodes/<slug>/material.json lists the candidates: {"films": [archive ids], "photos": [Commons files]}.
check() re-reads every licence and returns what may be used, with the reason for each.
"""
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core.logger import get_logger

log = get_logger("material")
ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))["material"]
UA = {"User-Agent": "germany-archive-channel/1.0 (https://github.com/beautyapp800-ctrl/germany-archive-channel)"}
USAGE = ROOT / "state" / "usage.json"
BLACKLIST = ROOT / "state" / "blacklist.json"     # sources a Content ID claim pointed at (owner 23.11)
FORBIDDEN = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in CFG["forbidden"]) + r"|newsreel library|filmed news release)\b",
                       re.I)
NAZI = re.compile(r"nazi|hitler|swastika|hakenkreuz|nsdap|reichsparteitag|wehrmacht|\bSS\b|gestapo|führer|fuehrer|"
                  r"concentration camp|konzentrationslager|holocaust|1933|1934|1935|1936|1937|1938|1939|1940|1941|1942|"
                  r"1943|1944", re.I)
FREE_URL = ("publicdomain/mark", "publicdomain/zero", "licenses/publicdomain", "licenses/by/")
VIDEO_EXT = (".mp4", ".mov", ".mpeg", ".mpg", ".ogv", ".avi", ".m4v", ".mkv")
_last = [0.0]


def _get(url, as_json=True, attempts=6, gap=1.2):
    for a in range(attempts):
        wait = gap - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
            return json.loads(raw) if as_json else raw
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and a < attempts - 1:
                time.sleep(min(120, 15 * (a + 1)))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if a < attempts - 1:
                time.sleep(10 * (a + 1))
                continue
            raise


# ---------------------------------------------------------------- usage (4-week rest)

def usage():
    try:
        return json.loads(USAGE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"films": {}, "photos": {}}


def resting(kind, key, slug, today=None):
    """True when another episode used this film/photo in the last rest days."""
    u = usage().get(kind, {}).get(key)
    if not u or u.get("slug") == slug:
        return False
    days = CFG["film_rest_days"] if kind == "films" else CFG["photo_rest_days"]
    today = today or dt.date.today()
    return (today - dt.date.fromisoformat(u["date"])).days < days


def mark_used(slug, films, photos, day=None):
    u = usage()
    day = (day or dt.date.today()).isoformat()
    for f in films:
        u.setdefault("films", {})[f] = {"slug": slug, "date": day}
    for p in photos:
        u.setdefault("photos", {})[p] = {"slug": slug, "date": day}
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    USAGE.write_text(json.dumps(u, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- blacklist

def blacklisted():
    try:
        return json.loads(BLACKLIST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"films": {}, "photos": {}}


def blacklist(kind, key, reason, day=None):
    """After a Content ID claim: the film/photo never comes back; the episode's fragment is replaced."""
    b = blacklisted()
    b.setdefault(kind, {})[key] = {"reason": reason, "date": (day or dt.date.today()).isoformat()}
    BLACKLIST.parent.mkdir(parents=True, exist_ok=True)
    BLACKLIST.write_text(json.dumps(b, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- films

def nara(naid):
    try:
        h = _get(f"https://catalog.archives.gov/proxy/records/search?naId={naid}")["body"]["hits"]["hits"]
    except Exception as e:                                           # noqa: BLE001
        return {"naId": naid, "status": "unknown", "error": str(e)[:120]}
    if not h:
        return {"naId": naid, "status": "not found"}
    r = h[0]["_source"]["record"]
    series = next((a for a in (r.get("ancestors") or []) if a.get("levelOfDescription") == "series"), {})
    group = next((a for a in (r.get("ancestors") or []) if a.get("levelOfDescription") == "recordGroup"), {})
    creators = [c.get("heading", "") for c in (series.get("creators") or [])]
    return {"naId": naid, "status": (r.get("useRestriction") or {}).get("status"),
            "specific": (r.get("useRestriction") or {}).get("specificUseRestrictions"),
            "series": series.get("title"), "record_group": group.get("recordGroupNumber"),
            "creators": creators, "title": r.get("title"), "page": f"catalog.archives.gov/id/{naid}"}


GOV = re.compile(r"Department of (the )?(Army|Defense|the Air Force|State)|Signal|Air Force|Information Agency|"
                 r"United States\. (Army|Air Force|Navy)|U\.S\. Army|US Army", re.I)


def film(identifier):
    """The film's metadata, files and licence decision {"ok", "basis", ...}."""
    d = _get(f"https://archive.org/metadata/{identifier}")
    m = d.get("metadata", {})
    text = " ".join(str(m.get(k, "")) for k in ("title", "description", "subject", "creator", "collection"))
    out = {"id": identifier, "title": m.get("title"), "date": m.get("date") or m.get("year"),
           "creator": m.get("creator"), "page": f"archive.org/details/{identifier}",
           "licenseurl": m.get("licenseurl"), "ok": False}
    if identifier in blacklisted().get("films", {}):
        out["why"] = "blacklisted after a Content ID claim"
        return out
    num = re.search(r"adc-?(\d+)", identifier, re.I)
    if num and int(num.group(1)) >= 10000:
        out["why"] = "111-ADC 10000+ (World in Film range)"
        return out
    if FORBIDDEN.search(text):
        out["why"] = f"forbidden source in the metadata ({FORBIDDEN.search(text).group(0)})"
        return out
    if NAZI.search(str(m.get("title", ""))):
        out["why"] = "Nazi period / symbols in the title"
        return out
    ids = re.findall(r"(?:catalog\.archives\.gov/id/|research\.archives\.gov/description/|National Archives Identifier:?\D{0,40})(\d{4,})", text)
    if ids:
        out["nara"] = nara(ids[0])
    lic = str(m.get("licenseurl") or "")
    lic_free = any(k in lic for k in FREE_URL) and not re.search(r"by-sa|by-nc|by-nd|/nc|/nd", lic)
    # owner 23.11: a US government department as the author in the NARA card (Army, Air Force, USIA ...),
    # whatever use status the card shows ("Restricted - Possibly" included); newsreels and commercial inserts never
    card = " ".join(out.get("nara", {}).get("creators") or [])
    gov = bool(GOV.search(str(m.get("creator") or "") + " " + card)) or (
        out.get("nara", {}).get("record_group") in (111, 342, 306, 330, 18))
    out["nara_status"] = out.get("nara", {}).get("status")
    if gov:
        out.update(ok=True, basis="US federal work, public domain (17 U.S.C. 105)")
    elif lic_free and not re.search(r"newsreel|march of time|pathe|movietone", text, re.I):
        out.update(ok=True, basis=f"marked {lic} on the item page")
    else:
        out["why"] = "no free licence and not a US federal work"
        return out
    vids = [f for f in d.get("files", []) if f.get("name", "").lower().endswith(VIDEO_EXT)]
    if not vids:
        out.update(ok=False, why="no video file")
        return out
    base = f"https://archive.org/download/{identifier}/"
    best = max(vids, key=lambda f: (f.get("source") == "original", int(f.get("width") or 0) * int(f.get("height") or 0),
                                     int(f.get("size") or 0)))
    small = min(vids, key=lambda f: int(f.get("size") or 1 << 40))
    out.update(best=base + urllib.parse.quote(best["name"]), proxy=base + urllib.parse.quote(small["name"]),
               size=[best.get("width"), best.get("height")])
    h = max(int(f.get("height") or 0) for f in vids)
    if h and h < 360:
        out.update(ok=False, why=f"only {h} lines: too soft for a 1080p picture")
    return out


# ---------------------------------------------------------------- photos

def _free(lic):
    l = lic.lower()
    if re.search(r"\bsa\b|by-sa|\bnc\b|-nc|\bnd\b|-nd|gfdl", l):
        return False
    return l.startswith(("public domain", "pd", "cc0", "no restrictions")) or bool(re.match(r"cc[ -]by[ -]\d", l))


def photos(files):
    """Licence of every Commons file read again from its page; free ones with a 330 px thumb url."""
    out = []
    for k in range(0, len(files), 40):
        part = files[k:k + 40]
        d = _get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "titles": "|".join(part), "prop": "imageinfo", "format": "json",
            "iiprop": "extmetadata|size|url", "iiurlwidth": 330}))
        for pg in d.get("query", {}).get("pages", {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            m = ii.get("extmetadata", {})
            g = lambda key: re.sub("<[^>]+>", "", m.get(key, {}).get("value", "")).strip()[:300]   # noqa: E731
            lic, desc = g("LicenseShortName"), g("ImageDescription")
            row = {"file": pg.get("title"), "licence": lic, "author": g("Artist"), "credit": g("Credit"),
                   "date": g("DateTimeOriginal"), "desc": desc, "page": str(ii.get("descriptionurl", "")).replace("https://", ""),
                   "url": ii.get("url"), "thumb": ii.get("thumburl"), "size": [ii.get("width"), ii.get("height")]}
            if not _free(lic):
                row["why"] = f"licence {lic!r}"
            elif NAZI.search(pg.get("title", "") + " " + desc):
                row["why"] = "Nazi period / symbols in title or description"
            elif FORBIDDEN.search(pg.get("title", "") + " " + g("Credit") + " " + g("Artist")):
                row["why"] = "forbidden source"
            elif (ii.get("width") or 0) < 900:
                row["why"] = "under 900 px"
            row["ok"] = "why" not in row
            out.append(row)
    return out


def download(url, dest, attempts=6):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 2000:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_get(url, as_json=False, attempts=attempts, gap=1.5))
    return dest


def check(slug, today=None):
    """{'films': [...ok films...], 'photos': [...ok photos...], 'refused': [...]} for the episode."""
    want = json.loads((ROOT / "episodes" / slug / "material.json").read_text(encoding="utf-8"))
    films, photos_ok, refused = [], [], []
    for i in want.get("films", []):
        f = film(i)
        if f["ok"] and resting("films", i, slug, today):
            f.update(ok=False, why="used by another episode in the last 4 weeks")
        (films if f["ok"] else refused).append(f)
        log.info("film %s: %s", i, f.get("basis") or f.get("why"))
    for p in photos(want.get("photos", [])):
        if p["ok"] and p["file"] in blacklisted().get("photos", {}):
            p.update(ok=False, why="blacklisted after a Content ID claim")
        if p["ok"] and resting("photos", p["file"], slug, today):
            p.update(ok=False, why="used by another episode in the last 4 weeks")
        (photos_ok if p["ok"] else refused).append(p)
    log.info("%s: %d films, %d photos usable; %d refused", slug, len(films), len(photos_ok), len(refused))
    return {"films": films, "photos": photos_ok, "refused": refused}
