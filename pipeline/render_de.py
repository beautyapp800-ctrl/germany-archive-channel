"""Pictures to video: film stretches restored, photos moved, overlays, sound.

Every shot fills the whole 16:9 frame (cover/crop): no bars, no blurred side panels, no
darkening vignette (owner 21.11). Film: pipeline/clips.cut (deflicker, gentle denoise,
two-pass stabilisation, Lanczos to 1920x1080 filling the frame, light sharpen) - classic
restoration only. Photo: a slow move (push-in, pull-out or pan; a portrait photo pans down
its height) rendered frame by frame with sub-pixel boxes, so it glides instead of stepping.

Overlays: the year of the picture (bottom left, small), the number tag of the line (yellow
sticker, top right) and the chapter title (lower third) on the chapter's first shot.
Sound: narration, a CC0 music bed under it, loudness -14 LUFS, true peak -1 dBTP.
"""
import json
import math
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.logger import get_logger

log = get_logger("render")
ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))
W, H, FPS = 1920, 1080, 30
FONT = str(ROOT / "assets" / "fonts" / "Anton-Regular.ttf")
YELLOW, WHITE, BLACK, RED = (255, 212, 0), (255, 255, 255), (0, 0, 0), (226, 30, 38)


def _ff(args, timeout=1800):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")
    return r.stderr


# ---------------------------------------------------------------- photos

def _ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _boxes(iw, ih, seed):
    """Start and end crop boxes (x0, y0, x1, y1) in image pixels, both exactly 16:9."""
    rnd = random.Random(seed)
    ar = W / H
    if iw / ih >= ar:
        bh, bw = ih, ih * ar
    else:
        bw, bh = iw, iw / ar
    portrait = ih > iw * 1.05
    if portrait:
        # a tall picture: the 16:9 window travels down (or up) its height
        top, bottom = 0.0, ih - bh
        y0, y1 = (top, bottom * 0.85) if rnd.random() < 0.7 else (bottom * 0.85, top)
        return (0, y0, bw, y0 + bh), (0, y1, bw, y1 + bh)
    z = 1.0 / rnd.uniform(1.10, 1.16)           # 10-16 % tighter at one end
    big = (iw / 2 - bw / 2, ih / 2 - bh / 2, iw / 2 + bw / 2, ih / 2 + bh / 2)
    sw, sh = bw * z, bh * z
    cx = iw / 2 + rnd.uniform(-0.5, 0.5) * (bw - sw)
    cy = ih / 2 + rnd.uniform(-0.5, 0.3) * (bh - sh)
    small = (cx - sw / 2, cy - sh / 2, cx + sw / 2, cy + sh / 2)
    mode = rnd.choice(["in", "out", "pan"])
    if mode == "in":
        return big, small
    if mode == "out":
        return small, big
    dx = (bw - sw) / 2
    left = (big[0] + dx * 0.2, small[1], big[0] + dx * 0.2 + sw, small[3])
    right = (big[2] - dx * 0.2 - sw, small[1], big[2] - dx * 0.2, small[3])
    return (left, right) if rnd.random() < 0.5 else (right, left)


def photo_clip(src, seconds, out, seed=0, trim=None):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if trim and tuple(trim) != (0.0, 0.0, 1.0, 1.0):
        # inside the scanned print's border (pipeline/frames_de.trim, found on the thumbnail)
        l, t, r, b = trim
        im = im.crop((round(l * im.width), round(t * im.height), round(r * im.width), round(b * im.height)))
    # keep the work size sane: 1.6x the output at most along the box's long side
    lim = 3600
    if max(im.size) > lim:
        k = lim / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    b0, b1 = _boxes(im.width, im.height, seed)
    n = max(1, round(seconds * FPS))
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-vf", "unsharp=5:5:0.45:5:5:0.0,format=yuv420p",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", str(out)], stdin=subprocess.PIPE)
    for f in range(n):
        t = _ease(f / max(1, n - 1))
        box = tuple(a + (b - a) * t for a, b in zip(b0, b1))
        p.stdin.write(im.resize((W, H), Image.BICUBIC, box=box).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError(f"photo clip {src} failed")
    return out


# ---------------------------------------------------------------- overlays

def _font(size):
    return ImageFont.truetype(FONT, size)


def overlay_png(shot, out):
    """One transparent 1920x1080 layer with the shot's year, tag and chapter title."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shot.get("year"):
        d.text((48, H - 46), str(shot["year"]), font=_font(40), fill=WHITE + (235,), stroke_width=3,
               stroke_fill=BLACK + (200,), anchor="ls")
    if shot.get("tag"):
        f = _font(78)
        tw = f.getlength(shot["tag"])
        x1, y0 = W - 70, 70
        x0, y1 = x1 - tw - 110, y0 + 118
        d.polygon([(x0, y0 + 59), (x0 + 50, y0), (x1, y0), (x1, y1), (x0 + 50, y1)], fill=YELLOW + (255,),
                  outline=BLACK + (255,), width=6)
        d.ellipse((x0 + 26, y0 + 49, x0 + 46, y0 + 69), fill=WHITE + (255,), outline=BLACK + (255,), width=3)
        d.text(((x0 + 60 + x1) / 2, y0 + 61), shot["tag"], font=f, fill=BLACK + (255,), anchor="mm")
    if shot.get("chapter_title"):
        f = _font(84)
        tw = f.getlength(shot["chapter_title"])
        d.rectangle((0, H - 300, tw + 150, H - 180), fill=RED + (235,))
        d.text((80, H - 240), shot["chapter_title"], font=f, fill=WHITE + (255,), anchor="lm")
    im.save(out)
    return out


def finish_shot(raw, shot, out, work):
    d = shot["end"] - shot["start"]
    layer = overlay_png(shot, Path(work) / (Path(out).stem + "_o.png"))
    fade = (f"[1:v]format=rgba,fade=t=in:st=0.15:d=0.35:alpha=1,fade=t=out:st={max(0.5, d - 0.45):.3f}:d=0.35:alpha=1[o];"
            f"[0:v][o]overlay=0:0,format=yuv420p")
    _ff(["-y", "-stream_loop", "-1", "-i", str(raw), "-loop", "1", "-i", str(layer), "-filter_complex", fade,
         "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-r", str(FPS), str(out)])
    return out


# ---------------------------------------------------------------- sound

def _lufs(path):
    err = _ff(["-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    return json.loads(err[err.rfind("{"):err.rfind("}") + 1])


def _norm(src, dest, target, tp=-1.5):
    m = _lufs(src)
    _ff(["-y", "-i", str(src), "-af",
         f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
         f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
         "-ar", "48000", "-ac", "2", str(dest)])
    return dest


def music_bed(tracks, seconds, work):
    """The CC0 tracks one after another (with a crossfade), looped to the length."""
    work = Path(work)
    files = [ROOT / "assets" / "music" / f"{t['id']}.mp3" for t in tracks]
    for t, f in zip(tracks, files):
        if not f.exists():
            subprocess.run(["curl", "-sSfL", "--retry", "4", "-A", "germany-archive-channel/1.0", "-o", str(f), t["url"]],
                           check=True)
    if len(files) == 1:
        one = files[0]
    else:
        one = work / "music_chain.wav"
        _ff(["-y", "-i", str(files[0]), "-i", str(files[1]), "-filter_complex", "[0:a][1:a]acrossfade=d=4[a]",
             "-map", "[a]", "-ar", "48000", "-ac", "2", str(one)])
    bed = work / "music_bed.wav"
    _ff(["-y", "-stream_loop", "-1", "-i", str(one), "-t", f"{seconds:.3f}", "-af",
         f"afade=t=in:d=2,afade=t=out:st={max(0, seconds - 4):.3f}:d=4", "-ar", "48000", "-ac", "2", str(bed)])
    return bed


def mix(narration, seconds, out, work):
    snd = CFG["sound"]
    work = Path(work)
    voice = _norm(narration, work / "voice48.wav", -16.0)
    bed = music_bed(CFG["music"]["tracks"], seconds, work)
    bed_n = _norm(bed, work / "bed_n.wav", -16.0 + snd["music_under_voice_db"])
    pre = work / "premix.wav"
    _ff(["-y", "-i", str(voice), "-i", str(bed_n), "-filter_complex",
         f"[0:a]apad=whole_dur={seconds:.3f}[v];[v][1:a]amix=inputs=2:duration=first:normalize=0[m]",
         "-map", "[m]", "-t", f"{seconds:.3f}", "-ar", "48000", "-ac", "2", str(pre)])
    return _norm(pre, out, snd["target_lufs"], snd["true_peak"] - 0.3)


def assemble(shot_files, audio, out, work):
    lst = Path(work) / "v.txt"
    lst.write_text("".join(f"file '{Path(v).resolve().as_posix()}'\n" for v in shot_files), encoding="utf-8")
    picture = Path(work) / "picture.mp4"
    _ff(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(picture)])
    _ff(["-y", "-i", str(picture), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
         "-b:v", "10M", "-maxrate", "14M", "-bufsize", "20M", "-c:a", "aac", "-b:a", "192k", "-shortest",
         "-movflags", "+faststart", str(out)], timeout=3600)
    return out
