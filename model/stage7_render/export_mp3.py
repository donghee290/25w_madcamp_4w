from __future__ import annotations
import subprocess
from pathlib import Path

def wav_to_mp3(wav_path: str, mp3_path: str, bitrate: str = "192k") -> None:
    wav = Path(wav_path)
    mp3 = Path(mp3_path)
    mp3.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        str(mp3),
    ]
    subprocess.run(cmd, check=True)