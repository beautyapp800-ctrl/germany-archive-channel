"""Three thumbnail candidates in the Yesterday in Color manner, with one big eye-catcher each.

Base: the episode's own best picture of the cover subject, improved with classic steps only
(autocontrast, contrast, sharpening, Lanczos enlargement; black-and-white stays black-and-white
under a warm grade, never painted in). The eye-catcher is the largest thing on the cover:
  A  cut-out hero: the subject's own pixels (rembg mask), much enlarged, white outline
  B  number tag: a yellow sticker with a figure the video says ("1.398 FLÜGE")
  C  red circle + arrow on the subject, with a stamp ("ECHT?")
Text is secondary: the year (yellow) and a 2-4 word hook (white), Anton with an outline, never
over the eye-catcher, never in the bottom-right corner (YouTube's running time).
Each candidate is checked at 320x180 and 210x118; the one whose eye-catcher is biggest and whose
words still read is chosen automatically.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FONT = str(ROOT / "assets" / "fonts" / "Anton-Regular.ttf")
W, H = 1280, 720
YELLOW, WHITE, RED, BLACK = (255, 212, 0), (255, 255, 255), (226, 30, 38), (0, 0, 0)


def _font(s):
    return ImageFont.truetype(FONT, s)


def is_bw(im):
    a = np.asarray(im.convert("RGB").resize((160, 90)), np.float32)
    return float(np.abs(a[..., 0] - a[..., 1]).mean() + np.abs(a[..., 1] - a[..., 2]).mean()) < 6


def enhance(im):
    bw = is_bw(im)
    im = ImageOps.autocontrast(im.convert("RGB"), cutoff=1)
    if bw:
        g = ImageOps.grayscale(im)
        im = ImageOps.colorize(g, black=(20, 16, 12), mid=(150, 118, 78), white=(255, 248, 228))
    else:
        im = ImageEnhance.Color(im).enhance(1.4)
    im = ImageEnhance.Contrast(im).enhance(1.2)
    return im.filter(ImageFilter.UnsharpMask(radius=2, percent=130, threshold=2))


def focus(im):
    """The box around the sizeable subjects (rembg) as fractions of the picture, or None."""
    try:
        from rembg import new_session, remove
        from scipy import ndimage
        small = im.convert("RGB").resize((640, max(1, round(640 * im.height / im.width))))
        a = np.array(remove(small, session=new_session("isnet-general-use")).getchannel("A")) > 60
        lab, n = ndimage.label(a)
        if n == 0:
            return None
        sizes = np.asarray(ndimage.sum(np.ones_like(a), lab, range(1, n + 1)))
        big = 1 + np.nonzero(sizes >= 0.15 * sizes.max())[0]       # every sizeable piece: plane AND crowd
        ys, xs = np.nonzero(np.isin(lab, big))
        if len(xs) < 300:
            return None
        return (xs.min() / a.shape[1], ys.min() / a.shape[0], (xs.max() + 1) / a.shape[1], (ys.max() + 1) / a.shape[0])
    except Exception:                                               # noqa: BLE001
        return None


def cover(im, size=(W, H), cy=0.45, box=None):
    """Fill the cover size; with a subject box, the crop slides so the subject stays whole
    (pilot 22.11: the C-54 lost its top on all three covers)."""
    s = max(size[0] / im.width, size[1] / im.height)
    im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
    x = (im.width - size[0]) // 2
    y = int((im.height - size[1]) * cy)
    if box:
        bx0, by0, bx1, by1 = box[0] * im.width, box[1] * im.height, box[2] * im.width, box[3] * im.height
        mx, my = size[0] * 0.04, size[1] * 0.05
        # keep the subject's top (heads, a plane) first, then as much of its bottom as fits
        y = min(max(y, by1 + my - size[1]), by0 - my)
        x = min(max(x, bx1 + mx - size[0]), bx0 - mx)
        x = int(max(0, min(im.width - size[0], x)))
        y = int(max(0, min(im.height - size[1], y)))
    return im.crop((x, y, x + size[0], y + size[1]))


def cutout(im):
    from rembg import new_session, remove
    from scipy import ndimage
    rgba = remove(im, session=new_session("isnet-general-use"))
    a = np.array(rgba.getchannel("A"))
    lab, n = ndimage.label(a > 40)
    if n == 0:
        return None
    sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
    keep = lab == (1 + int(np.argmax(sizes)))
    if keep.mean() < 0.02:
        return None
    a = np.where(ndimage.binary_dilation(keep, iterations=3), a, 0).astype("uint8")
    rgba.putalpha(Image.fromarray(a))
    return rgba.crop(rgba.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox())


def outlined(rgba, px=12):
    a = rgba.getchannel("A").point(lambda v: 255 if v > 90 else 0)
    size = (rgba.width + 4 * px, rgba.height + 4 * px)
    m = Image.new("L", size, 0)
    m.paste(a, (2 * px, 2 * px))
    ring = m.filter(ImageFilter.MaxFilter(2 * px + 1))
    shadow = ring.filter(ImageFilter.GaussianBlur(px)).point(lambda v: int(v * 0.6))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", size, (0, 0, 0, 255)), (px // 2, px), shadow)
    out.paste(Image.new("RGBA", size, WHITE + (255,)), (0, 0), ring)
    out.alpha_composite(rgba, (2 * px, 2 * px))
    return out


def _text(d, xy, s, size, fill, anchor="la"):
    d.text(xy, s, font=_font(size), fill=fill, stroke_width=max(4, size // 12), stroke_fill=BLACK, anchor=anchor)


def _fit(s, width, start):
    size = start
    while _font(size).getlength(s) > width and size > 24:
        size -= 4
    return size


def tag(label, h=150):
    f = _font(int(h * 0.56))
    w = int(f.getlength(label) + h * 0.95)
    im = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(12 + h // 2, 12), (w + 12, 12), (w + 12, h + 12), (12 + h // 2, h + 12), (12, 12 + h // 2)],
              fill=YELLOW, outline=BLACK, width=7)
    d.ellipse((12 + h * 0.3, 12 + h * 0.42, 12 + h * 0.46, 12 + h * 0.58), fill=WHITE, outline=BLACK, width=4)
    d.text((12 + h * 0.6 + (w - h * 0.6) / 2, 12 + h / 2), label, font=f, fill=BLACK, anchor="mm")
    return im.rotate(-7, expand=True, resample=Image.BICUBIC)


def stamp(label, size=300):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((8, 8, size - 8, size - 8), fill=(255, 255, 255, 225), outline=RED, width=size // 16)
    f = _font(_fit(label, size * 0.66, int(size * 0.34)))
    d.text((size / 2, size / 2), label, font=f, fill=RED, anchor="mm")
    return im.rotate(12, expand=True, resample=Image.BICUBIC)


def _subject_box(im):
    """Where the cut-out finds the subject in the base (x0, y0, x1, y1), or the centre."""
    try:
        from rembg import new_session, remove
        a = np.array(remove(im.resize((640, 360)), session=new_session("isnet-general-use")).getchannel("A")) > 60
        ys, xs = np.nonzero(a)
        if len(xs) > 500:
            k = im.width / 640
            return (xs.min() * k, ys.min() * k, xs.max() * k, ys.max() * k)
    except Exception:                                               # noqa: BLE001
        pass
    return (W * 0.35, H * 0.25, W * 0.75, H * 0.75)


def candidate_a(base, hero_src, year, hook, box=None):
    bg = cover(enhance(base), box=box).convert("RGBA")
    bg = Image.alpha_composite(bg, Image.new("RGBA", bg.size, (0, 0, 0, 40)))
    hero = cutout(enhance(hero_src))
    if hero is None:
        return None, 0.0
    hero = outlined(hero, 14)
    s = min(W * 0.62 / hero.width, H * 0.80 / hero.height)
    hero = hero.resize((int(hero.width * s), int(hero.height * s)), Image.LANCZOS)
    bg.alpha_composite(hero, (W - hero.width - 40, (H - hero.height) // 2 - 20))
    d = ImageDraw.Draw(bg)
    _text(d, (44, 40), year, 120, YELLOW)
    lines = hook.split(" ", 1) if len(hook) > 10 else [hook]
    y = 200
    for ln in lines:
        size = _fit(ln, W - hero.width - 100, 150)
        _text(d, (44, y), ln, size, WHITE)
        y += size + 14
    return bg.convert("RGB"), hero.width * hero.height / (W * H)


def candidate_b(base, year, hook, label, box=None):
    bg = cover(enhance(base), box=box).convert("RGBA")
    t = tag(label, 190)
    if t.width > W * 0.8:
        k = W * 0.8 / t.width
        t = t.resize((int(t.width * k), int(t.height * k)), Image.LANCZOS)
    bg.alpha_composite(t, ((W - t.width) // 2, H // 2 - t.height // 2 + 30))
    d = ImageDraw.Draw(bg)
    _text(d, (44, 36), year, 110, YELLOW)
    _text(d, (W - 44, 50), hook, _fit(hook, W * 0.55, 110), WHITE, anchor="ra")
    return bg.convert("RGB"), t.width * t.height / (W * H)


def candidate_c(base, year, hook, label, box=None):
    bg = cover(enhance(base), box=box).convert("RGBA")
    x0, y0, x1, y1 = _subject_box(bg.convert("RGB"))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = max(90, min(260, max(x1 - x0, y1 - y0) * 0.6))
    # the whole circle stays on the cover (pilot: it ran off the top edge)
    r = min(r, (H - 48) / 2)
    cx, cy = min(max(cx, r + 24), W - r - 24), min(max(cy, r + 24), H - r - 24)
    d = ImageDraw.Draw(bg)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=RED, width=16)
    st = stamp(label, 270)
    left_side = cx > W / 2
    sx = 40 if left_side else W - st.width - 40
    sy = H - st.height - 30
    ax, ay = (sx + st.width * 0.85, sy + st.height * 0.2) if left_side else (sx + st.width * 0.15, sy + st.height * 0.2)
    tx, ty = cx + (-1 if left_side else 1) * r * 0.72, cy + r * 0.72
    d.line((ax, ay, tx, ty), fill=RED, width=22)
    ang = math.atan2(ty - ay, tx - ax)
    d.polygon([(tx, ty), (tx - 60 * math.cos(ang - 0.5), ty - 60 * math.sin(ang - 0.5)),
               (tx - 60 * math.cos(ang + 0.5), ty - 60 * math.sin(ang + 0.5))], fill=RED)
    bg.alpha_composite(st, (int(sx), int(sy)))
    _text(d, (44, 30), year, 110, YELLOW)
    # the hook goes where it covers neither the circle nor the stamp
    size = _fit(hook, W * 0.5, 105)
    tw = _font(size).getlength(hook)
    spots = [(W - 44, 40, "ra"), (44, 170, "la"), (W - 44, H - size - 60, "ra"), (44, H - size - 60, "la")]

    def clear(x, y, anchor):
        rx0 = x - tw if anchor == "ra" else x
        rect = (rx0 - 20, y - 10, rx0 + tw + 20, y + size + 30)
        nx, ny = min(max(cx, rect[0]), rect[2]), min(max(cy, rect[1]), rect[3])
        hits_circle = (nx - cx) ** 2 + (ny - cy) ** 2 < (r + 20) ** 2
        hits_stamp = not (rect[2] < sx or rect[0] > sx + st.width or rect[3] < sy or rect[1] > sy + st.height)
        return not hits_circle and not hits_stamp
    x, y, anchor = next((sp for sp in spots if clear(*sp)), spots[0])
    _text(d, (x, y), hook, size, WHITE, anchor=anchor)
    return bg.convert("RGB"), math.pi * r * r / (W * H)


def readable(im):
    """Sharpness of the small versions (higher = edges and words survive the shrink)."""
    out = {}
    for w, h in ((320, 180), (210, 118)):
        g = np.asarray(im.resize((w, h), Image.LANCZOS).convert("L"), np.float32)
        out[f"{w}x{h}"] = round(float(np.var(np.diff(g, axis=0)) + np.var(np.diff(g, axis=1))), 1)
    return out


def make(base, hero_src, meta, out_dir, a_base=None):
    """a_base: background for the cut-out cover when the hero is cut from the base picture
    itself (the same plane twice looked odd in the pilot)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    c = meta["cover"]
    year = meta.get("year_label", "")
    made = []
    box = focus(base)
    ab = a_base if a_base is not None else base
    a, share = candidate_a(ab, hero_src, year, c["hooks"][0], box=focus(ab) if a_base is not None else box)
    if a is not None:
        made.append(("A_hero", a, share, c["hooks"][0]))
    b, share = candidate_b(base, year, c["hooks"][1] if len(c["hooks"]) > 1 else c["hooks"][0], c["tag"], box=box)
    made.append(("B_tag", b, share, c["tag"]))
    cc, share = candidate_c(base, year, c["hooks"][2] if len(c["hooks"]) > 2 else c["hooks"][0], c["stamp"], box=box)
    made.append(("C_circle", cc, share, c["stamp"]))
    report = []
    for name, im, share, words in made:
        f = out_dir / f"cover_{name}.jpg"
        im.save(f, quality=92)
        report.append({"file": f.name, "eye_catcher_share": round(share, 3), "words": words, **readable(im)})
    sheet = Image.new("RGB", (3 * 330 + 20, 2 * 190 + 30), (40, 40, 40))
    for k, (_, im, _, _) in enumerate(made):
        sheet.paste(im.resize((320, 180), Image.LANCZOS), (10 + k * 330, 10))
        sheet.paste(im.resize((210, 118), Image.LANCZOS), (10 + k * 330, 210))
    sheet.save(out_dir / "check_small.jpg", quality=90)
    # the biggest eye-catcher whose small version is not mush wins
    ok = [r for r in report if r["210x118"] > 80] or report
    best = max(ok, key=lambda r: r["eye_catcher_share"] + 0.0005 * r["210x118"])
    (out_dir / "thumbnail.jpg").write_bytes((out_dir / best["file"]).read_bytes())
    return {"candidates": report, "chosen": best["file"]}
