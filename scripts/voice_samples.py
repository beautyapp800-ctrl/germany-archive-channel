"""Voice audition for the German channel (runs on GitHub, never on the owner's PC).

Stage 1: one probe sentence with every licence-clean German Piper voice and every
speaker of de_DE-mls-medium, scored with UTMOS22 (predicted naturalness, 1-5).
Stage 2: the full sample text with the best voices -> MP3 + ranking.json.
Excluded: thorsten* (used by Urzeit-Archiv), pavoque (CC BY-NC-SA).
"""
import json, subprocess, sys, wave
from pathlib import Path
import numpy as np

OUT = Path("out/voices"); OUT.mkdir(parents=True, exist_ok=True)
MODELS = Path("models"); MODELS.mkdir(exist_ok=True)
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE"
VOICES = {  # name: (path, licence of the training data)
    "kerstin-medium": ("kerstin/medium/de_DE-kerstin-medium", "CC0 (dataset-voice-kerstin)"),
    "kerstin-low": ("kerstin/low/de_DE-kerstin-low", "CC0 (dataset-voice-kerstin)"),
    "karlsson-low": ("karlsson/low/de_DE-karlsson-low", "M-AILABS, BSD-style, commercial use allowed"),
    "ramona-low": ("ramona/low/de_DE-ramona-low", "M-AILABS, BSD-style, commercial use allowed"),
    "eva_k-x_low": ("eva_k/x_low/de_DE-eva_k-x_low", "M-AILABS, BSD-style, commercial use allowed"),
    "mls-medium": ("mls/medium/de_DE-mls-medium", "MLS (openslr 94), CC BY 4.0 - credit in description"),
}
PROBE = "Im Sommer neunzehnhundertachtundvierzig kostete ein Kilo Butter auf dem Schwarzmarkt fast dreihundert Mark."
FULL = (
    "Berlin, im Juni neunzehnhundertachtundvierzig. Die Stadt liegt in Trümmern, und über Nacht wird sie zur Insel. "
    "Keine Straße, keine Schiene, kein Schiff kommt mehr durch. Zwei Millionen Menschen brauchen jeden Tag Kohle, Mehl und Milch. "
    "Die Antwort kommt aus der Luft: Alle drei Minuten landet in Tempelhof ein Flugzeug. "
    "Aber wie lange kann man eine ganze Stadt aus dem Himmel versorgen? Und was kostete das Leben dort wirklich?"
)


def fetch(path):
    onnx = MODELS / (Path(path).name + ".onnx")
    for suf in (".onnx", ".onnx.json"):
        dst = MODELS / (Path(path).name + suf)
        if not dst.exists():
            subprocess.run(["curl", "-sSfL", "-o", str(dst), f"{HF}/{path}{suf}"], check=True)
    return onnx


def synth(voice, text, sid=None):
    from piper import SynthesisConfig
    cfg = SynthesisConfig(speaker_id=sid)
    a = np.concatenate([c.audio_float_array for c in voice.synthesize(text, cfg)]).astype(np.float32)
    return a, voice.config.sample_rate


def mos(pred, a, sr):
    import torch, torchaudio
    w = torch.from_numpy(a)[None]
    if sr != 16000:
        w = torchaudio.functional.resample(w, sr, 16000)
    return float(pred(w, 16000).item())


def save(a, sr, name):
    wav = OUT / f"{name}.wav"
    with wave.open(str(wav), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    mp3 = OUT / f"{name}.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5",
                    "-ar", "44100", "-b:a", "128k", str(mp3)], check=True)
    wav.unlink()


def main():
    import torch
    from piper import PiperVoice
    pred = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True)
    rows = []
    for name, (path, lic) in VOICES.items():
        v = PiperVoice.load(str(fetch(path)))
        sids = [None] if v.config.num_speakers <= 1 else sorted(v.config.speaker_id_map.items(), key=lambda x: x[1])
        for s in sids:
            label, sid = (name, None) if s is None else (f"{name}-spk{s[0]}", s[1])
            a, sr = synth(v, PROBE, sid)
            rows.append({"voice": label, "model": name, "sid": sid, "licence": lic, "sr": sr, "utmos_probe": round(mos(pred, a, sr), 3)})
            print(rows[-1], flush=True)
    rows.sort(key=lambda r: -r["utmos_probe"])
    loaded = {}
    for r in rows[:8]:  # full sample for the best 8; the owner hears the top 3
        v = loaded.setdefault(r["model"], PiperVoice.load(str(fetch(VOICES[r["model"]][0]))))
        a, sr = synth(v, FULL, r["sid"])
        r["utmos_full"] = round(mos(pred, a, sr), 3)
        save(a, sr, r["voice"])
    top = sorted(rows[:8], key=lambda r: -r["utmos_full"])
    json.dump({"text": FULL, "top": top, "all_probe": rows}, open(OUT / "ranking.json", "w"), indent=1, ensure_ascii=False)
    for r in top:
        print("FULL", r["voice"], r["utmos_full"], r["licence"])


if __name__ == "__main__":
    sys.exit(main())
