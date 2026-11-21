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


def cover(im, size=(W, H), cy=0.45):
    s = max(size[0] / im.width, size[1] / im.height)
    im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
    x = (im.width - size[0]) // 2
    y = int((im.height - size[1]) * cy)
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


def candidate_a(base, hero_src, year, hook):
    bg = cover(enhance(base)).convert("RGBA")
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


def candidate_b(base, year, hook, label):
    bg = cover(enhance(base)).convert("RGBA")
    t = tag(label, 190)
    if t.width > W * 0.8:
        k = W * 0.8 / t.width
        t = t.resize((int(t.width * k), int(t.height * k)), Image.LANCZOS)
    bg.alpha_composite(t, ((W - t.width) // 2, H // 2 - t.height // 2 + 30))
    d = ImageDraw.Draw(bg)
    _text(d, (44, 36), year, 110, YELLOW)
    _text(d, (W - 44, 50), hook, _fit(hook, W * 0.55, 110), WHITE, anchor="ra")
    return bg.convert("RGB"), t.width * t.height / (W * H)


def candidate_c(base, year, hook, label):
    bg = cover(enhance(base)).convert("RGBA")
    x0, y0, x1, y1 = _subject_box(bg.convert("RGB"))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = max(90, min(260, max(x1 - x0, y1 - y0) * 0.6))
    d = ImageDraw.Draw(bg)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=RED, width=16)
    ax, ay = max(60, cx - r - 230), min(H - 150, cy + r + 40)
    d.line((ax, ay, cx - r * 0.72, cy + r * 0.72), fill=RED, width=22)
    ang = math.atan2(cy + r * 0.72 - ay, cx - r * 0.72 - ax)
    tip = (cx - r * 0.72, cy + r * 0.72)
    d.polygon([tip, (tip[0] - 60 * math.cos(ang - 0.5), tip[1] - 60 * math.sin(ang - 0.5)),
               (tip[0] - 60 * math.cos(ang + 0.5), tip[1] - 60 * math.sin(ang + 0.5))], fill=RED)
    st = stamp(label, 270)
    bg.alpha_composite(st, (40, H - st.height - 30))
    _text(d, (44, 30), year, 110, YELLOW)
    _text(d, (W - 44, 40), hook, _fit(hook, W * 0.5, 105), WHITE, anchor="ra")
    return bg.convert("RGB"), math.pi * r * r / (W * H)


def readable(im):
    """Sharpness of the small versions (higher = edges and words survive the shrink)."""
    out = {}
    for w, h in ((320, 180), (210, 118)):
        g = np.asarray(im.resize((w, h), Image.LANCZOS).convert("L"), np.float32)
        out[f"{w}x{h}"] = round(float(np.var(np.diff(g, axis=0)) + np.var(np.diff(g, axis=1))), 1)
    return out


def make(base, hero_src, meta, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    c = meta["cover"]
    year = meta.get("year_label", "")
    made = []
    a, share = candidate_a(base, hero_src, year, c["hooks"][0])
    if a is not None:
        made.append(("A_hero", a, share, c["hooks"][0]))
    b, share = candidate_b(base, year, c["hooks"][1] if len(c["hooks"]) > 1 else c["hooks"][0], c["tag"])
    made.append(("B_tag", b, share, c["tag"]))
    cc, share = candidate_c(base, year, c["hooks"][2] if len(c["hooks"]) > 2 else c["hooks"][0], c["stamp"])
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
