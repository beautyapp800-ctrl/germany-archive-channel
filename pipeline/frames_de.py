"""Picture checks before a frame enters the plan (pilot 22.11: QA failed on night shots and
on scanned prints whose mount, white margin or coloured edge showed in the frame).

  trim(img)    the box inside a photo's scan border (uniform, very bright/dark or coloured
               edge lines in a black-and-white print), plus a small safety margin
  verdict(img) None when the picture can fill a 16:9 frame cleanly, else the reason:
               too dark, too flat, or the same edge faults the final QA would fail on
"""
import numpy as np
from PIL import Image, ImageOps

from pipeline import qa_de

MAX_TRIM = 0.2          # never more than 20 % from one side
MARGIN = 0.02           # extra 2 % inside a found border (per pass)


def _arrays(img):
    im = ImageOps.exif_transpose(img).convert("RGB")
    k = 400 / max(im.size)
    if k < 1:
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.BILINEAR)
    rgb = np.asarray(im, np.float32)
    gray = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    sat = rgb.max(2) - rgb.min(2)
    return gray, sat


def _border_lines(gray, sat, mono, strict=False):
    """Per line (rows of the array): True where the line looks like scan border.

    strict (film frames): only a truly even black/white bar or a coloured edge counts,
    so an overcast sky or a dark foreground is not taken for a border."""
    m, s, c = gray.mean(1), gray.std(1), sat.mean(1)
    coloured = mono & (c > 45)
    if strict:
        return ((s < 5) & ((m < 18) | (m > 235))) | coloured
    flat = s < 9
    bright = (m > 222) & (s < 30)
    dark = (m < 26) & (s < 22)
    return flat | bright | dark | coloured


def _edge(lines, limit):
    """How many lines from the start belong to the border (short interruptions allowed)."""
    cut, gap = 0, 0
    for i in range(limit):
        if lines[i]:
            cut, gap = i + 1, 0
        else:
            gap += 1
            if gap > 3:
                break
    return cut


def trim(img, strict=False, passes=3):
    """(left, top, right, bottom) as fractions of the image to keep.

    A mounted print has layers (red mount, white paper, dark photo edge): each pass peels
    the outer one off, until a pass finds nothing more."""
    box = _inside_mount(img)
    for _ in range(passes):
        l, t, r, b = _trim_once(crop(img, box), strict)
        if (l, t, r, b) == (0.0, 0.0, 1.0, 1.0):
            break
        w, h = box[2] - box[0], box[3] - box[1]
        box = (box[0] + l * w, box[1] + t * h, box[0] + r * w, box[1] + b * h)
        if box[2] - box[0] < 0.5 or box[3] - box[1] < 0.5:
            break
    if box != (0.0, 0.0, 1.0, 1.0) and not strict:
        # a found border leaves a soft edge line behind: 1.5 % more off every side
        w, h = box[2] - box[0], box[3] - box[1]
        box = (box[0] + 0.015 * w, box[1] + 0.015 * h, box[2] - 0.015 * w, box[3] - 0.015 * h)
    return tuple(round(v, 4) for v in box)


def _longest_run(flags):
    best, cur, start = (0, 0), 0, 0
    for i, f in enumerate(list(flags) + [False]):
        if f:
            if cur == 0:
                start = i
            cur += 1
            if cur > best[1] - best[0]:
                best = (start, i + 1)
        else:
            cur = 0
    return best


def _inside_mount(img):
    """A black-and-white print on a coloured mount (Signal Corps prints: red card with a typed
    caption): the photo is the largest block of rows and columns with almost no colour."""
    gray, sat = _arrays(img)
    h, w = gray.shape
    centre = sat[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    col = sat > 40
    if np.median(centre) > 14 or col.mean() < 0.03:
        return (0.0, 0.0, 1.0, 1.0)
    r0, r1 = _longest_run(col.mean(1) < 0.08)
    if r1 - r0 < h * 0.4:
        return (0.0, 0.0, 1.0, 1.0)
    c0, c1 = _longest_run(col[r0:r1].mean(0) < 0.08)
    if c1 - c0 < w * 0.4:
        return (0.0, 0.0, 1.0, 1.0)
    return (c0 / w, r0 / h, c1 / w, r1 / h)


def _trim_once(img, strict=False):
    gray, sat = _arrays(img)
    h, w = gray.shape
    mono = float(np.median(sat)) < 14
    lim_h, lim_w = int(h * MAX_TRIM), int(w * MAX_TRIM)
    top = _edge(_border_lines(gray, sat, mono, strict), lim_h)
    bottom = _edge(_border_lines(gray[::-1], sat[::-1], mono, strict), lim_h)
    left = _edge(_border_lines(gray.T, sat.T, mono, strict), lim_w)
    right = _edge(_border_lines(gray.T[::-1], sat.T[::-1], mono, strict), lim_w)
    box = (left / w + (MARGIN if left else 0), top / h + (MARGIN if top else 0),
           1 - right / w - (MARGIN if right else 0), 1 - bottom / h - (MARGIN if bottom else 0))
    return tuple(round(v, 4) for v in box)


def crop(img, box):
    l, t, r, b = box
    return img.crop((round(l * img.width), round(t * img.height), round(r * img.width), round(b * img.height)))


def _cover_169(img):
    w, h = img.size
    if w / h > 16 / 9:
        nw = h * 16 / 9
        img = img.crop((round((w - nw) / 2), 0, round((w + nw) / 2), h))
    else:
        nh = w * 9 / 16
        img = img.crop((0, round((h - nh) / 2), w, round((h + nh) / 2)))
    return img.resize((qa_de.FW, qa_de.FH), Image.BILINEAR)


def verdict(img):
    rgb = np.asarray(_cover_169(ImageOps.exif_transpose(img).convert("RGB")), np.float32)
    g = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    if g.mean() < 45 or (g < 35).mean() > 0.6 or np.percentile(g, 95) < 100:
        return "too dark"
    if g.std() < 18:
        return "too flat"
    return qa_de.frame_problem(g) or qa_de.coloured_edge(rgb.max(2) - rgb.min(2))


def check_file(path, film=False):
    """{'ok', 'why', 'trim'} for one keyframe or photo thumbnail.

    A photo is cropped inside its scan border; a film frame cannot be (the whole stretch
    plays), so a film frame that shows a border is refused instead."""
    img = Image.open(path)
    box = trim(img, strict=film)
    if film:
        if max(box[0], box[1], 1 - box[2], 1 - box[3]) > 0.035:
            return {"ok": False, "why": "border in the film frame", "trim": box}
        box = (0.0, 0.0, 1.0, 1.0)
    if box[2] - box[0] < 0.55 or box[3] - box[1] < 0.55:
        return {"ok": False, "why": "mostly border", "trim": box}
    why = verdict(crop(img, box))
    return {"ok": why is None, "why": why, "trim": box}
