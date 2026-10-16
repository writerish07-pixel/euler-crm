"""Rebuild Akar Euler verify MP3s — conversational Hindi for phone IVR.

Needs: pip install edge-tts, ffmpeg on PATH.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import exotel as exo  # noqa: E402

VOICE = "hi-IN-SwaraNeural"
RATE = "+8%"
PITCH = "+2Hz"


async def _synth(text: str, dest: Path):
    import edge_tts
    raw = dest.with_suffix(".raw.mp3")
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    await communicate.save(str(raw))
    subprocess.check_call([
        "ffmpeg", "-y", "-i", str(raw),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,silenceremove=start_periods=1:start_silence=0.15:start_threshold=-40dB",
        "-ar", "16000", "-ac", "1", "-b:a", "48k",
        str(dest),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raw.unlink(missing_ok=True)


async def main():
    exo.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    keep = {"prompt"}  # original amount-ask clip
    for name, text in exo.SPOKEN_HI.items():
        dest = exo.AUDIO_DIR / f"{name}.mp3"
        if name in keep:
            print(f"keeping {dest.name}")
            continue
        print(f"building {dest.name} …")
        await _synth(text, dest)
        print(f"  {dest.stat().st_size} bytes")


if __name__ == "__main__":
    asyncio.run(main())
