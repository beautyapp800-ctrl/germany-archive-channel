"""Channel art options (3 avatars, 3 banners) in the cover style - runs on GitHub.

Bases are real photos with a licence checked on Commons at run time (PD, CC0,
CC BY only; SA/NC/ND refused). Enhancement is classic only (autocontrast,
saturation, unsharp, Lanczos), the cut-out hero is the photo's own pixels
(rembg mask) with a white outline - nothing is generated or painted in.
"""
import io, json, math, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

OUT = Path("out/branding"); OUT.mkdir(parents=True, exist_ok=True)
FONT = "assets/fonts/Anton-Regular.ttf"
UA = {"User-Agent": "germany-archive-channel/1.0 (github actions; licence check)"}
YELLOW, WHITE, RED, BLACK = (255, 212, 0), (255, 255, 255), (226, 30, 38), (0, 0, 0)
NAMES = ["ALS OMA JUNG WAR", "WIRTSCHAFTSWUNDER-ARCHIV", "VON TRÜMMERN ZUM WUNDER"]
WANT = {  # key: Commons search (first hit with a free licence is taken)
    "beetle": "1000000th Beetle",
    "tempelhof": "C-54 landing on old Tempelhof runway as work continues",
    "ruins": "Germany Under Allied Occupation, 1945 BU8684",
    "rhine": "Rijnvaart reportage vanaf sleepboot Damco 9 West-Duitsland Drachenfels",
    "c54": "C-54 landing at Tempelhof 1948",
}


def api(p, n=0):
    time.sleep(1.5)
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({**p, "format": "json"})
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=90))
    except urllib.error.HTTPError as e:
        if e.code == 429 and n < 5:
            time.sleep(30 * (n + 1))
            return api(p, n + 1)
        raise


def download(url, n=0):
    time.sleep(2)
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
    except urllib.error.HTTPError as e:
        if e.code == 429 and n < 5:
            time.sleep(30 * (n + 1))
            return download(url, n + 1)
        raise


def free(lic):
    l = lic.lower()
    if re.search(r"\bsa\b|by-sa|\bnc\b|-nc|\bnd\b|-nd|gfdl", l):
        return False
    return l.startswith("public domain") or l.startswith("pd") or l.startswith("cc0") or bool(re.match(r"cc[ -]by[ -]\d", l))


def fetch(key, q):
    d = api({"action": "query", "generator": "search", "gsrsearch": "filetype:bitmap " + q, "gsrnamespace": 6,
             "gsrlimit": 5, "prop": "imageinfo", "iiprop": "extmetadata|url|size"})
    for pg in sorted(d["query"]["pages"].values(), key=lambda p: p["index"]):
        ii = pg["imageinfo"][0]
        m = ii["extmetadata"]
        g = lambda k: re.sub("<[^>]+>", "", m.get(k, {}).get("value", "")).strip()[:300]
        if not free(g("LicenseShortName")):
            continue
        raw = download(ii["url"])  # the original file: odd thumbnail widths are throttled by Wikimedia
        src = {"key": key, "file": pg["title"], "page": ii["descriptionurl"].replace("https://", ""),
               "licence": g("LicenseShortName"), "author": g("Artist"), "credit": g("Credit"),
               "date": g("DateTimeOriginal"), "size": [ii["width"], ii["height"]]}
        return Image.open(io.BytesIO(raw)).convert("RGB"), src
    raise SystemExit(f"no free image for {key}")


def enhance(im, sat=1.45, con=1.18, bri=1.06):
    im = ImageOps.autocontrast(im, cutoff=1)
    im = ImageEnhance.Color(im).enhance(sat)
    im = ImageEnhance.Contrast(im).enhance(con)
    im = ImageEnhance.Brightness(im).enhance(bri)
    return im.filter(ImageFilter.UnsharpMask(radius=2.2, percent=140, threshold=2))


def cover(im, size, cx=0.5, cy=0.5):
    w, h = size
    s = max(w / im.width, h / im.height)
    im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
    x = int((im.width - w) * cx)
    y = int((im.height - h) * cy)
    return im.crop((x, y, x + w, y + h))


def warm_tint(im):
    """Black-and-white photos get a warm gold grade - a tint, never presented as real colour."""
    g = ImageOps.grayscale(im)
    return ImageOps.colorize(g, black=(25, 18, 10), mid=(170, 120, 60), white=(255, 246, 220))


def cutout(im):
    from rembg import remove, new_session
    import numpy as np
    from scipy import ndimage
    rgba = remove(im, session=new_session("isnet-general-use"))
    a = np.array(rgba.getchannel("A"))
    lab, n = ndimage.label(a > 40)
    if n > 1:  # keep only the hero: the largest piece of the mask (no stray bystanders)
        sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
        keep = lab == (1 + int(np.argmax(sizes)))
        a = np.where(ndimage.binary_dilation(keep, iterations=3), a, 0).astype("uint8")
        rgba.putalpha(Image.fromarray(a))
    bbox = rgba.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    return rgba.crop(bbox)


def outlined(rgba, px=14):
    a = rgba.getchannel("A").point(lambda v: 255 if v > 90 else 0)
    size = (rgba.width + 4 * px, rgba.height + 4 * px)
    m = Image.new("L", size, 0)
    m.paste(a, (2 * px, 2 * px))
    ring = m.filter(ImageFilter.MaxFilter(2 * px + 1))
    shadow = ring.filter(ImageFilter.GaussianBlur(px)).point(lambda v: int(v * 0.55))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", size, (0, 0, 0, 255)), (px // 2, px), shadow)
    out.paste(Image.new("RGBA", size, WHITE + (255,)), (0, 0), ring)
    out.alpha_composite(rgba, (2 * px, 2 * px))
    return out


def text(d, xy, s, size, fill, stroke=None, anchor="mm"):
    f = ImageFont.truetype(FONT, size)
    sw = stroke if stroke is not None else max(3, size // 14)
    d.text(xy, s, font=f, fill=fill, stroke_width=sw, stroke_fill=BLACK, anchor=anchor)


def fit_size(s, width, start):
    size = start
    while ImageFont.truetype(FONT, size).getlength(s) > width and size > 20:
        size -= 4
    return size


def tag(label, h=150, fill=YELLOW):
    """Price-tag sticker."""
    f = ImageFont.truetype(FONT, int(h * 0.55))
    w = int(f.getlength(label) + h * 0.9)
    im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(10 + h // 2, 10), (w + 10, 10), (w + 10, h + 10), (10 + h // 2, h + 10), (10, 10 + h // 2)]
    d.polygon(pts, fill=fill, outline=BLACK, width=6)
    d.ellipse((10 + h * 0.32, 10 + h * 0.42, 10 + h * 0.48, 10 + h * 0.58), fill=WHITE, outline=BLACK, width=4)
    d.text((10 + h * 0.62 + (w - h * 0.62) / 2, 10 + h / 2), label, font=f, fill=BLACK, anchor="mm")
    return im.rotate(-8, expand=True, resample=Image.BICUBIC)


def stamp(label, size=420, color=RED):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((8, 8, size - 8, size - 8), fill=(255, 255, 255, 215), outline=color, width=size // 18)
    d.ellipse((size * 0.11, size * 0.11, size * 0.89, size * 0.89), outline=color, width=size // 40)
    f = ImageFont.truetype(FONT, fit_size(label, size * 0.66, int(size * 0.34)))
    d.text((size / 2, size / 2), label, font=f, fill=color, anchor="mm")
    return im.rotate(14, expand=True, resample=Image.BICUBIC)


def sunburst(size, c1=(255, 200, 0), c2=(255, 140, 0), rays=24):
    im = Image.new("RGB", size, c1)
    d = ImageDraw.Draw(im)
    cx, cy, r = size[0] / 2, size[1] / 2, max(size) * 1.2
    for i in range(1, rays, 2):
        a0, a1 = 2 * math.pi * i / rays, 2 * math.pi * (i + 1) / rays
        d.polygon([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                   (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=c2)
    return im


def paste_fit(canvas, rgba, box):
    x0, y0, x1, y1 = box
    s = min((x1 - x0) / rgba.width, (y1 - y0) / rgba.height)
    r = rgba.resize((int(rgba.width * s), int(rgba.height * s)), Image.LANCZOS)
    canvas.alpha_composite(r, (int(x0 + (x1 - x0 - r.width) / 2), int(y0 + (y1 - y0 - r.height) / 2)))


def main():
    # photos were fetched with fetch() (licence checked) and committed to branding/src:
    # Wikimedia throttles downloads from GitHub runner addresses
    srcs = json.load(open("branding/src/sources.json", encoding="utf-8"))
    imgs = {s["key"]: Image.open(s["local"]).convert("RGB") for s in srcs}
    json.dump(srcs, open(OUT / "sources.json", "w"), indent=1, ensure_ascii=False)
    beetle = outlined(cutout(enhance(imgs["beetle"])), 16)
    plane = outlined(cutout(enhance(imgs["c54"])), 12)

    # avatars 800x800
    a = sunburst((800, 800)).convert("RGBA")
    paste_fit(a, beetle, (40, 150, 760, 650))
    ImageDraw.Draw(a).ellipse((6, 6, 794, 794), outline=RED, width=26)
    a.convert("RGB").save(OUT / "avatar_1_kaefer.png")
    a = sunburst((800, 800), (90, 180, 255), (40, 130, 230)).convert("RGBA")
    paste_fit(a, plane, (10, 120, 790, 560))
    text(ImageDraw.Draw(a), (400, 650), "1948", 190, YELLOW)
    a.convert("RGB").save(OUT / "avatar_2_luftbruecke.png")
    a = cover(enhance(warm_tint(imgs["ruins"])), (800, 800)).convert("RGBA")
    st = stamp("45-70", 640, RED)
    a.alpha_composite(st, ((800 - st.width) // 2, (800 - st.height) // 2))
    a.convert("RGB").save(OUT / "avatar_3_stempel.png")

    # banners 2560x1440, safe area 1546x423 centred
    sx0, sy0, sx1, sy1 = 507, 508, 2053, 931
    for i, (bk, name) in enumerate(zip(["tempelhof", "rhine", "frankfurt"], NAMES), 1):
        base = warm_tint(imgs[bk])  # all three are black-and-white photos
        b = cover(enhance(base, sat=1.5), (2560, 1440)).convert("RGBA")
        band = Image.new("RGBA", (2560, 380), (0, 0, 0, 120))
        b.alpha_composite(band, (0, 530))
        d = ImageDraw.Draw(b)
        hero_w = 560
        tx0 = sx0 + (hero_w if i != 3 else 0)
        tx1 = sx1 - (380 if i == 3 else 0)
        size = fit_size(name, tx1 - tx0 - 40, 190)
        text(d, ((tx0 + tx1) / 2, 650), name, size, WHITE)
        text(d, ((tx0 + tx1) / 2, 815), "DEUTSCHLAND 1945-1970", 92, YELLOW)
        text(d, ((tx0 + tx1) / 2, 900), "NEUE DOKUS: DI + FR 18 UHR", 46, WHITE, 3)
        if i in (1, 2):
            paste_fit(b, beetle, (sx0 - 40, sy0 - 40, sx0 + hero_w, sy1 + 30))
        if i == 1:
            b.alpha_composite(tag("NR. 1.000.000", 90), (sx0 + 40, sy1 - 150))
        elif i == 2:
            st = stamp("ECHT?", 250)
            b.alpha_composite(st, (sx0 - 30, sy0 - 50))
        else:
            paste_fit(b, plane, (sx1 - 420, sy0 - 60, sx1 + 60, sy1 + 20))
        b.convert("RGB").save(OUT / f"banner_{i}.jpg", quality=92)

    # readability: avatars as circles at 400/98/48 px, banners' safe area (what a phone shows)
    sheet = Image.new("RGB", (1500, 1280), (40, 40, 40))
    for row, f in enumerate(sorted(OUT.glob("avatar_*.png"))):
        im, x, y = Image.open(f), 20, 20 + row * 420
        for s in (400, 98, 48):
            r = im.resize((s, s), Image.LANCZOS)
            m = Image.new("L", (s, s), 0)
            ImageDraw.Draw(m).ellipse((0, 0, s, s), fill=255)
            sheet.paste(r, (x, y), m)
            x += s + 30
    for row, f in enumerate(sorted(OUT.glob("banner_*.jpg"))):
        sheet.paste(Image.open(f).crop((sx0, sy0, sx1, sy1)).resize((773, 211)), (700, 20 + row * 420))
    sheet.save(OUT / "check_readability.jpg", quality=90)


if __name__ == "__main__":
    sys.exit(main())
