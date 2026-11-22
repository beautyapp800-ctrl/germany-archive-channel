"""Candidate pictures for a topic: US-government films on archive.org and Commons files.

    from pipeline import find_material_de
    find_material_de.find(topic)      # writes episodes/<slug>/material.json

Films: archive.org search over the US-government collections (Army, Air Force, National Archives,
FedFlix / usgovfilms) for the topic's film_queries, dated 1944-1972 when a date is known; every hit
goes through material_de.film() (licence decision, newsreel and World-in-Film exclusion, blacklist,
4-week rest). Photos: the topic's Commons categories (one level of subcategories) and Commons file
searches; material_de.photos() later re-reads every licence at the source, so this list is generous.
"""
import json
import re
import urllib.parse
from pathlib import Path

from core.logger import get_logger
from pipeline import material_de

log = get_logger("find-material")
ROOT = Path(__file__).resolve().parent.parent
GOV = ('(collection:usgovfilms OR collection:fedflix OR creator:"United States. Army" OR '
       'creator:"United States. Air Force" OR creator:"National Archives" OR creator:"United States Information Agency")')
COMMONS = "https://commons.wikimedia.org/w/api.php?"


def films(queries, want=14, scan=40):
    seen, out, tried = {}, [], 0
    for q in queries:
        words = " AND ".join(f'"{w}"' if " " in w else w for w in q.split())
        sq = f"({words}) AND mediatype:movies AND {GOV}"
        d = material_de._get("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
            {"q": sq, "fl[]": ["identifier", "title", "date", "year"], "rows": 30, "sort[]": "downloads desc",
             "output": "json"}, doseq=True))
        for x in d.get("response", {}).get("docs", []):
            y = re.search(r"(19[4-7]\d)", str(x.get("date") or x.get("year") or x.get("title") or ""))
            if y and not 1944 <= int(y.group(1)) <= 1972:
                continue
            seen.setdefault(x["identifier"], q)
    for ident in list(seen):
        if len(out) >= want or tried >= scan:
            break
        tried += 1
        try:
            f = material_de.film(ident)
        except Exception as e:                                       # noqa: BLE001
            log.warning("film %s: %s", ident, str(e)[:100])
            continue
        if f["ok"] and not material_de.resting("films", ident, ""):
            out.append(ident)
        else:
            log.info("film %s left out: %s", ident, f.get("why") or "resting")
    log.info("%d film candidates, %d checked, %d kept", len(seen), tried, len(out))
    return out


def _members(cat, kind):
    out, cont = [], {}
    while len(out) < 600:
        d = material_de._get(COMMONS + urllib.parse.urlencode(
            {"action": "query", "list": "categorymembers", "cmtitle": cat, "cmtype": kind, "cmlimit": 200,
             "format": "json", **cont}))
        out += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        cont = d.get("continue") or {}
        if not cont:
            break
    return out


def photos(categories, queries, cap=450):
    files = []
    for c in categories:
        try:
            files += _members(c, "file")
            for sub in _members(c, "subcat")[:12]:
                files += _members(sub, "file")[:150]
        except Exception as e:                                       # noqa: BLE001
            log.warning("category %s: %s", c, str(e)[:100])
    for q in queries:
        for off in (0, 50, 100):
            try:
                d = material_de._get(COMMONS + urllib.parse.urlencode(
                    {"action": "query", "list": "search", "srsearch": f"{q} filetype:bitmap", "srnamespace": 6,
                     "srlimit": 50, "sroffset": off, "format": "json"}))
            except Exception as e:                                   # noqa: BLE001
                log.warning("search %s: %s", q, str(e)[:100])
                break
            hits = [h["title"] for h in d.get("query", {}).get("search", [])]
            files += hits
            if len(hits) < 50:
                break
    uniq = list(dict.fromkeys(f for f in files if re.search(r"\.(jpe?g|png|tiff?)$", f, re.I)))
    uniq = [f for f in uniq if not material_de.resting("photos", f, "")
            and f not in material_de.blacklisted().get("photos", {})]
    log.info("%d photo candidates", len(uniq))
    return uniq[:cap]


def find(topic):
    q = topic.get("film_queries") or []
    cq = topic.get("commons_queries") or [topic["name"].split(":")[0], *(topic.get("wikipedia") or [])[:2]]
    m = {"films": films(q), "photos": photos(topic.get("commons_categories") or [], cq)}
    d = ROOT / "episodes" / topic["slug"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "material.json").write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return m
