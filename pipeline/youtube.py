"""YouTube for "Als Oma jung war": private uploads with a publishAt, never twice.

Token: YT_TOKEN_JSON (hypothetica-511509 client, this channel's own token), from the environment only.
Slots (config/channel.json "schedule"): Sunday 17:00 Europe/Berlin, at least min_lead_minutes ahead,
one video a slot. Captions de + en go up with captions.insert (never burnt in).

Anti-duplicate (owner 17.11): before an upload the channel's COMPLETE uploads list is read (every
page, retried, checked against the ids the state already knows). A video whose description carries
this episode's marker "[ref: germany/<slug>]" (or has the same title) is the episode already
uploaded. If the list cannot be read in full, or anything looks wrong, Doubt is raised: nothing is
uploaded. The slots are taken from the channel's own publishAt dates, not from the state alone.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from core.logger import get_logger

log = get_logger("youtube")
ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))["schedule"]
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/youtube.force-ssl"]


class Doubt(RuntimeError):
    """Not sure the channel was read in full: no upload (owner 17.11: when unsure, do not upload)."""


REF = "[ref: germany/{slug}]"


def _retry(fn, what, tries=4):
    import time
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:                                       # noqa: BLE001
            last = e
            log.warning("%s failed (%d/%d): %s", what, i + 1, tries, str(e)[:160])
            time.sleep(2 * 3 ** i)
    raise Doubt(f"{what} failed {tries} times: {str(last)[:200]}")


def all_uploads(yt, known_ids=()):
    """Every video of the channel (private and scheduled too): snippet + status, each page retried.
    Raises Doubt when the count is short of what YouTube reports or an id the state knows is missing."""
    ch = _retry(lambda: yt.channels().list(part="contentDetails", mine=True).execute(), "channel")["items"][0]
    pl = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok, total = [], None, None
    while True:
        r = _retry(lambda t=tok: yt.playlistItems().list(part="contentDetails", playlistId=pl, maxResults=50,
                                                         pageToken=t).execute(), "uploads page")
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        total = (r.get("pageInfo") or {}).get("totalResults", total)
        tok = r.get("nextPageToken")
        if not tok:
            break
    if total is not None and len(ids) < total:
        raise Doubt(f"the uploads list has {len(ids)} of {total} videos")
    vids = []
    for k in range(0, len(ids), 50):
        part = ids[k:k + 50]
        got = _retry(lambda p=part: yt.videos().list(part="snippet,status", id=",".join(p)).execute(),
                     "video details")["items"]
        vids += got
    seen = {v["id"] for v in vids}
    missing = [i for i in known_ids if i not in seen]
    if missing:
        raise Doubt(f"the state knows videos the list lacks: {missing}")
    out = []
    for v in vids:
        st, sn = v["status"], v["snippet"]
        out.append({"id": v["id"], "title": sn.get("title", ""), "description": sn.get("description", ""),
                    "privacy": st.get("privacyStatus"), "publish_at": st.get("publishAt"),
                    "published_at": sn.get("publishedAt")})
    log.info("the channel has %d videos (read in full)", len(out))
    return out


def find_existing(videos, slug, title):
    """The video of this episode if the channel has it: by the marker in the description, else by title."""
    ref = REF.format(slug=slug)
    for v in videos:
        if ref in v["description"]:
            return v
    for v in videos:
        if v["title"].strip() == title.strip():
            return v
    return None


def channel_dates(videos):
    """The dates the channel already holds a slot on: publishAt of scheduled ones, the publish
    time of public and unlisted ones."""
    out = []
    for v in videos:
        t = v["publish_at"] or (v["published_at"] if v["privacy"] in ("public", "unlisted") else None)
        if t:
            out.append(t)
    return out


def has_token():
    return bool(os.environ.get("YT_TOKEN_JSON", "").strip())


def service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    d = json.loads(os.environ["YT_TOKEN_JSON"])
    cred = Credentials(token=None, refresh_token=d["refresh_token"], client_id=d["client_id"],
                       client_secret=d["client_secret"], token_uri=d.get("token_uri", "https://oauth2.googleapis.com/token"),
                       scopes=d.get("scopes") or SCOPES)
    return build("youtube", "v3", credentials=cred, cache_discovery=False)


def next_slot(taken=(), now=None):
    """The nearest free Sunday 17:00 Berlin slot, as an aware UTC datetime."""
    tz = ZoneInfo(CFG["timezone"])
    now = now or datetime.now(timezone.utc)
    hh, mm = (int(x) for x in CFG["local_time"].split(":"))
    days = {datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(tz).date() for t in taken}
    d = now.astimezone(tz).date()
    for _ in range(90):
        slot = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
        if slot.weekday() in CFG["weekdays"] and slot.astimezone(timezone.utc) - now >= timedelta(minutes=CFG["min_lead_minutes"]) \
                and d not in days:
            return slot.astimezone(timezone.utc)
        d += timedelta(days=1)
    raise RuntimeError("no free slot in 90 days")


def upload(video, title, description, tags, publish_at=None, yt=None, synthetic=False):
    """Private, with publishAt when given. The caller has already read the whole channel
    (all_uploads / find_existing); this only sends. Category 27, language de, not for kids;
    containsSyntheticMedia only when the episode says so (colour added by AI)."""
    from googleapiclient.http import MediaFileUpload
    yt = yt or service()
    up = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))["upload"]
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": bool(up["made_for_kids"]),
              "containsSyntheticMedia": bool(synthetic)}
    if publish_at:
        status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"snippet": {"title": title[:100], "description": description[:5000], "tags": tags[:30],
                        "categoryId": up["category_id"], "defaultLanguage": up["language"],
                        "defaultAudioLanguage": up["language"]},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    log.info("uploaded %s", resp["id"])
    return resp["id"]


def set_captions(video_id, files, yt=None):
    """captions.insert: {"de": path, "en": path}. A missing track is a warning, never a lost video."""
    from googleapiclient.http import MediaFileUpload
    yt = yt or service()
    done = {}
    for lang, path in files.items():
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": video_id, "language": lang,
                                 "name": {"de": "Deutsch", "en": "English"}.get(lang, lang), "isDraft": False}},
                                 media_body=MediaFileUpload(str(path), mimetype="application/octet-stream")).execute()
            done[lang] = "ok"
        except Exception as e:                                       # noqa: BLE001
            done[lang] = f"failed: {str(e)[:120]}"
            log.warning("captions %s for %s: %s", lang, video_id, str(e)[:160])
    return done


def set_thumbnail(video_id, path, yt=None):
    from googleapiclient.http import MediaFileUpload
    (yt or service()).thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(path))).execute()


def schedule(video_id, publish_at, yt=None):
    yt = yt or service()
    st = yt.videos().list(part="status", id=video_id).execute()["items"][0]["status"]
    keep = {k: v for k, v in st.items() if k in ("embeddable", "license", "publicStatsViewable",
                                                 "selfDeclaredMadeForKids", "containsSyntheticMedia")}
    keep.update({"privacyStatus": "private", "publishAt": publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")})
    yt.videos().update(part="status", body={"id": video_id, "status": keep}).execute()
