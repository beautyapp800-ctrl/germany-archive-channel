"""German narration with Piper (voice chosen by the owner 22.11: de_DE-karlsson-low).

    audio, sr, timeline = synthesize(load(), script)

The script is episodes/<slug>/script.json: chapters of lines. Every line is
spoken as its own sentence; a short pause follows each line and a longer one
opens each chapter. The timeline gives every line's start and end on the
narration's clock, which the shot plan, the subtitles and the chapters use.
Numbers are written out in the script itself, so Piper never guesses them.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "channel.json").read_text(encoding="utf-8"))["voice"]
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/"
MODELS = ROOT / "assets" / "models" / "piper"


def fetch():
    MODELS.mkdir(parents=True, exist_ok=True)
    name = Path(CFG["path"]).name
    for suf in (".onnx", ".onnx.json"):
        dst = MODELS / (name + suf)
        if not dst.exists() or dst.stat().st_size < 1000:
            subprocess.run(["curl", "-sSfL", "--retry", "4", "-o", str(dst), HF + CFG["path"] + suf], check=True)
    return MODELS / (name + ".onnx")


def load():
    from piper import PiperVoice
    return PiperVoice.load(str(fetch()))


def _trim(a, sr, thr=0.006):
    idx = np.nonzero(np.abs(a) > thr)[0]
    if not len(idx):
        return a
    return a[max(0, idx[0] - int(0.02 * sr)): idx[-1] + int(0.06 * sr)]


def sentence(voice, text, scale=None):
    from piper import SynthesisConfig
    cfg = SynthesisConfig(length_scale=scale or CFG.get("length_scale", 1.0))
    a = np.concatenate([c.audio_float_array for c in voice.synthesize(text, cfg)]).astype(np.float32)
    return _trim(a, voice.config.sample_rate)


def lines_of(script):
    out = []
    for ci, ch in enumerate(script["chapters"]):
        for li, ln in enumerate(ch["lines"]):
            out.append({"chapter": ci, "chapter_title": ch["title"], "line": li, **ln})
    return out


def synthesize(voice, script, scale=None):
    sr = voice.config.sample_rate
    parts, timeline, t = [], [], 0.0
    lp, cp = CFG.get("line_pause_s", 0.28), CFG.get("chapter_pause_s", 0.9)
    for k, ln in enumerate(lines_of(script)):
        pause = cp if (ln["line"] == 0 and k) else (0.15 if k == 0 else lp)
        parts.append(np.zeros(int(sr * pause), np.float32))
        t += pause
        a = sentence(voice, ln["text"], scale)
        timeline.append({**ln, "start": round(t, 3), "end": round(t + len(a) / sr, 3)})
        parts.append(a)
        t += len(a) / sr
    parts.append(np.zeros(int(sr * 1.2), np.float32))
    audio = np.concatenate(parts)
    peak = float(np.max(np.abs(audio))) or 1.0
    return (audio / peak * 0.89).astype(np.float32), sr, timeline
