"""Build one episode of the German channel, stage by stage (one job of episode-de.yml each).

    python automation/build_de.py <slug> prepare      # narration, licences, film scan, shot plan
    python automation/build_de.py <slug> cut <k> <n>  # shots k, k+n, ... restored / moved, with overlays
    python automation/build_de.py <slug> render       # assembly, sound, QA, covers, subtitles, description

episodes/<slug>/script.json and material.json are in the repository; build/ and out/ live on
the runner and travel between jobs as artifacts.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.logger import get_logger  # noqa: E402

log = get_logger("build_de")


def paths(slug):
    e = ROOT / "episodes" / slug
    return e, e / "build", e / "out"


def stage_prepare(slug):
    import soundfile as sf
    from core import narrate_de
    from PIL import Image
    from pipeline import clips, frames_de, material_de, plan_de

    e, b, _ = paths(slug)
    b.mkdir(parents=True, exist_ok=True)
    script = json.loads((e / "script.json").read_text(encoding="utf-8"))
    ep = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))["episode"]
    voice = narrate_de.load()
    audio, sr, tl = narrate_de.synthesize(voice, script)
    secs = len(audio) / sr
    if secs < ep["minutes_min"] * 60 or secs > ep["minutes_max"] * 60:
        # one gentle retime before giving up: Piper's length_scale within 0.92-1.10
        goal = (ep["minutes_min"] + 0.6) * 60 if secs < ep["minutes_min"] * 60 else (ep["minutes_max"] - 0.6) * 60
        scale = max(0.92, min(1.10, goal / secs))
        log.warning("narration %.1f min; again with length_scale %.2f", secs / 60, scale)
        audio, sr, tl = narrate_de.synthesize(voice, script, scale)
        secs = len(audio) / sr
    sf.write(b / "narration.wav", audio, sr)
    (b / "timeline.json").write_text(json.dumps(tl, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("narration %.2f min, %d lines", secs / 60, len(tl))
    if not ep["minutes_min"] * 60 <= secs <= ep["minutes_max"] * 60:
        raise RuntimeError(f"LENGTH: narration {secs / 60:.1f} min")

    mat = material_de.check(slug)
    (b / "material.json").write_text(json.dumps(mat, indent=1, ensure_ascii=False), encoding="utf-8")
    cands, refused = [], {}
    for f in mat["films"]:
        try:
            scan = b / "scan" / f["id"]
            proxy = material_de.download(f["proxy"], scan / "proxy.mp4")
            ok = _clean_seconds(proxy, scan / "sec")
            for a, z, kf in _clean_pieces(clips.shots(proxy, scan, max_shots=60), ok, scan / "sec", refused):
                uses = max(1, int((z - a) // 4.4))
                cands.append({"kind": "film", "id": f"{f['id']}@{a:.1f}", "film_id": f["id"], "src": f["best"],
                              "start": a, "end": z, "kf": str(kf), "uses": uses,
                              "year": plan_de.year_of(f.get("date")) or plan_de.year_of(f.get("title"))})
        except Exception as ex:                                      # noqa: BLE001
            log.warning("film %s not scanned: %s", f["id"], ex)
    for k, p in enumerate(mat["photos"]):
        if not p.get("thumb"):
            continue
        try:
            th = material_de.download(p["thumb"], b / "thumbs" / f"p{k:04d}.jpg")
        except Exception as ex:                                      # noqa: BLE001
            log.warning("photo %s: %s", p["file"], ex)
            continue
        chk = frames_de.check_file(th)
        if not chk["ok"]:
            refused[chk["why"]] = refused.get(chk["why"], 0) + 1
            continue
        if chk["trim"] != (0.0, 0.0, 1.0, 1.0):
            trimmed = th.with_name(th.stem + "_t.jpg")
            frames_de.crop(Image.open(th).convert("RGB"), chk["trim"]).save(trimmed, quality=92)
            th = trimmed
        cands.append({"kind": "photo", "id": p["file"], "src": p, "kf": str(th), "trim": chk["trim"],
                      "year": plan_de.year_of(p.get("date")) or plan_de.year_of(p.get("file")),
                      "size": p.get("size")})
    log.info("pictures refused by the frame check: %s", refused)
    film_secs = sum(c["end"] - c["start"] for c in cands if c["kind"] == "film")
    log.info("candidates: %d film shots (%.0f s), %d photos", sum(c["kind"] == "film" for c in cands), film_secs,
             sum(c["kind"] == "photo" for c in cands))
    plan = plan_de.plan(tl, cands, year=script.get("year_label", "1948"))
    (b / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


def _clean_seconds(proxy, sec_dir):
    """{second: True/False}: one frame per second of the film through the frame check
    (too dark, too flat, a bar or a scanned print's border = False)."""
    from pipeline import frames_de
    sec_dir.mkdir(parents=True, exist_ok=True)
    if not any(sec_dir.glob("s_*.jpg")):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(proxy), "-vf",
                        "fps=1,scale=320:-2", "-q:v", "4", str(sec_dir / "s_%05d.jpg")], check=True, timeout=3600)
    return {int(f.stem[2:]) - 1: frames_de.check_file(f, film=True)["ok"] for f in sorted(sec_dir.glob("s_*.jpg"))}


def _clean_pieces(shots, ok, sec_dir, refused, min_len=2.5):
    """The scanned shots cut down to their stretches where every second passed the check."""
    import math
    for a, z, kf in shots:
        run = []
        for t in list(range(math.ceil(a), math.floor(z) + 1)) + [None]:
            if t is not None and ok.get(t, False):
                run.append(t)
                continue
            if run:
                s0, s1 = max(a, run[0] - 0.4), min(z, run[-1] + 0.4)
                if s1 - s0 >= min_len:
                    mid = run[len(run) // 2]
                    k = kf if s0 <= (a + z) / 2 <= s1 else sec_dir / f"s_{mid + 1:05d}.jpg"
                    yield round(s0, 2), round(s1, 2), k
                else:
                    refused["short clean stretch"] = refused.get("short clean stretch", 0) + 1
            if t is not None:
                refused["film second refused"] = refused.get("film second refused", 0) + 1
            run = []


def _name(key):
    import hashlib
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:16] + ".img"


def _hires(p, dest):
    from pipeline import material_de
    url = p["url"]
    w = (p.get("size") or [0])[0] or 0
    if url.lower().endswith((".tif", ".tiff")) or w > 3200:
        # a standard Commons thumbnail size: large originals and TIFFs are not fetched whole
        url = p["thumb"].replace("/330px-", "/1920px-") if p.get("thumb") else url
    return material_de.download(url, dest)


def stage_cut(slug, k, n):
    from pipeline import clips, render_de
    _, b, _ = paths(slug)
    plan = json.loads((b / "plan.json").read_text(encoding="utf-8"))
    work = b / f"cut_{k}"
    work.mkdir(parents=True, exist_ok=True)
    (b / "shots").mkdir(exist_ok=True)
    for i, s in list(enumerate(plan["shots"]))[k::n]:
        out = b / "shots" / f"v_{i:04d}.mp4"
        if out.exists():
            continue
        d = s["end"] - s["start"]
        raw = work / f"raw_{i:04d}.mp4"
        if s["kind"] == "film":
            clips.cut(s["src"], s["src_start"], d + 0.3, raw, work / "c", sound=False)
        else:
            src = _hires(s["src"], b / "photos" / _name(s["id"]))
            render_de.photo_clip(src, d + 0.1, raw, seed=i, trim=s.get("trim"))
        render_de.finish_shot(raw, s, out, work)
        raw.unlink(missing_ok=True)
    return 0


def contact_sheet(plan, b, out):
    """Every shot's frame with its time and line, for a human look (and the Nazi-symbol review)."""
    from PIL import Image, ImageDraw
    shots = plan["shots"]
    cols, tw, th = 8, 240, 135
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 18)), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for i, s in enumerate(shots):
        f = b / "shots" / f"v_{i:04d}.mp4"
        jpg = b / "sheet" / f"s_{i:04d}.jpg"
        jpg.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1.0", "-i", str(f), "-frames:v", "1", "-vf",
                        f"scale={tw}:{th}", str(jpg)])
        x, y = (i % cols) * tw, (i // cols) * (th + 18)
        if jpg.exists():
            sheet.paste(Image.open(jpg), (x, y))
        d.text((x + 3, y + th + 2), f"{int(s['start'] // 60)}:{int(s['start'] % 60):02d} {s['kind'][0]} {s['score']:.3f}",
               fill=(255, 255, 0))
    sheet.save(out, quality=85)


def stage_render(slug):
    from pipeline import cover_de, describe_de, frames_de, plan_de, qa_de, render_de, subs_de
    from PIL import Image
    e, b, out = paths(slug)
    out.mkdir(parents=True, exist_ok=True)
    script = json.loads((e / "script.json").read_text(encoding="utf-8"))
    plan = json.loads((b / "plan.json").read_text(encoding="utf-8"))
    tl = json.loads((b / "timeline.json").read_text(encoding="utf-8"))
    mat = json.loads((b / "material.json").read_text(encoding="utf-8"))
    shots = [b / "shots" / f"v_{i:04d}.mp4" for i in range(len(plan["shots"]))]
    missing = [str(s) for s in shots if not s.exists()]
    if missing:
        raise RuntimeError(f"{len(missing)} shots missing, e.g. {missing[:3]}")
    total = plan["shots"][-1]["end"]
    work = b / "render"
    work.mkdir(exist_ok=True)
    audio = render_de.mix(b / "narration.wav", total, work / "mix.wav", work)
    video = render_de.assemble(shots, audio, out / "video.mp4", work)
    qa = qa_de.check(video, plan, tl)
    contact_sheet(plan, b, out / "contact_sheet.jpg")

    # covers: the episode's own pictures that best show the cover subject
    hero_txt = plan_de.prompt(script["cover"]["hero"], script.get("year_label", ""))
    frames = [s["kf"] for s in plan["shots"]]
    S = plan_de.score_matrix([hero_txt], frames)[0]
    order = sorted(range(len(frames)), key=lambda k: -S[k])
    base_shot = plan["shots"][order[0]]
    hero_shot = next((plan["shots"][k] for k in order if plan["shots"][k]["kind"] == "photo"), base_shot)

    def big(s):
        if s["kind"] == "photo":
            im = Image.open(_hires(s["src"], b / "photos" / _name(s["id"]))).convert("RGB")
            return frames_de.crop(im, s["trim"]) if s.get("trim") else im
        i = plan["shots"].index(s)
        jpg = work / f"cover_src_{i}.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1.2", "-i", str(shots[i]), "-frames:v", "1", str(jpg)])
        return Image.open(jpg).convert("RGB")
    a_base = None
    if hero_shot is base_shot or hero_shot["id"] == base_shot["id"]:
        alt = next((plan["shots"][k] for k in order if plan["shots"][k]["id"] != base_shot["id"]), None)
        a_base = big(alt) if alt else None
    covers = cover_de.make(big(base_shot), big(hero_shot), script, out, a_base=a_base)

    (out / "subtitles_de.srt").write_text(subs_de.srt(tl, "text"), encoding="utf-8")
    (out / "subtitles_en.srt").write_text(subs_de.srt(tl, "en"), encoding="utf-8")
    used_ids = {s.get("film_id") for s in plan["shots"] if s["kind"] == "film"}
    used_films = [dict(f, basis_de="gemeinfrei, Werk der US-Regierung" if "federal" in f.get("basis", "") else f.get("basis"))
                  for f in mat["films"] if f["id"] in used_ids]
    used_ph = {s["id"] for s in plan["shots"] if s["kind"] == "photo"}
    used_photos = [p for p in mat["photos"] if p["file"] in used_ph]
    desc = describe_de.description(script, tl, used_films, used_photos, slug)
    meta = {"title": script["title"], "description": desc,
            "tags": script.get("tags") or ["Nachkriegszeit", "Geschichte Deutschland", "Archivfilm"],
            "category_id": "27", "language": "de", "made_for_kids": False, "contains_synthetic_media": False,
            "problems": describe_de.problems(script["title"], desc)}
    (out / "metadata.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "sources.json").write_text(json.dumps({"films": used_films, "photos": used_photos,
                                                  "refused": mat.get("refused", [])}, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    qa["covers"] = covers
    qa["metadata_problems"] = meta["problems"]
    qa["share_photos"] = round(len(used_ph) and sum(s["kind"] == "photo" for s in plan["shots"]) / len(plan["shots"]), 2)
    (out / "qa.json").write_text(json.dumps(qa, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("%s rendered; QA %s", slug, "passed" if qa["passed"] and not meta["problems"] else "FAILED")
    return 0 if qa["passed"] and not meta["problems"] else 2


def main():
    slug, stage = sys.argv[1], sys.argv[2]
    if stage == "cut":
        return stage_cut(slug, int(sys.argv[3]), int(sys.argv[4]))
    return {"prepare": stage_prepare, "render": stage_render}[stage](slug)


if __name__ == "__main__":
    sys.exit(main())
