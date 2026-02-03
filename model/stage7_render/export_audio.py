from __future__ import annotations
import subprocess
from pathlib import Path

def convert_audio(input_path: str, output_path: str, codec: str = "", bitrate: str = "192k") -> None:
    """
    General purpose audio conversion using ffmpeg.
    If codec is empty, ffmpeg auto-selects based on extension.
    """
    inp = Path(input_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(inp),
    ]

    if codec:
        cmd.extend(["-codec:a", codec])
        
    # bitrate option (mainly for lossy formats like mp3, ogg, etc.)
    # We apply it generally, though valid only for some encoders.
    # For lossless (flac, wav), bitrate might be ignored or warn.
    if bitrate and out.suffix.lower() in [".mp3", ".ogg", ".m4a"]:
        cmd.extend(["-b:a", bitrate])

    cmd.append(str(out))
    
    # Run silently-ish
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def export_as(wav_path: str, target_format: str, out_path: str) -> None:
    """
    Export wav_path to out_path with target_format.
    Supported: wav, mp3, flac, ogg, m4a
    """
    fmt = target_format.lower().replace(".", "")
    
    if fmt == "wav":
        # If input is already wav and path matches, do nothing or copy
        # Usually rendering produces wav directly, so we might just rename if needed.
        # But here we assume out_path is the final destination.
        if Path(wav_path).resolve() != Path(out_path).resolve():
             # Just copy or use ffmpeg to copy
             convert_audio(wav_path, out_path, codec="pcm_s16le")
    elif fmt == "mp3":
        convert_audio(wav_path, out_path, codec="libmp3lame")
    elif fmt == "flac":
        convert_audio(wav_path, out_path, codec="flac")
    elif fmt == "ogg":
        convert_audio(wav_path, out_path, codec="libvorbis")
    elif fmt == "m4a":
        convert_audio(wav_path, out_path, codec="aac", bitrate="192k")
    else:
        raise ValueError(f"Unsupported format: {fmt}")
