from __future__ import annotations
import argparse
from pathlib import Path

import sys
# Add model dir to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from stage7_render.audio_renderer import render_wav_from_event_grid
from stage7_render.export_audio import export_as

AUDIO_EXTS = ["wav", "mp3", "flac", "ogg", "m4a"]

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--grid_json", type=str, required=True)
    p.add_argument("--event_grid_json", type=str, required=True)
    p.add_argument("--sample_root", type=str, default="examples/input_samples")
    p.add_argument("--out_dir", type=str, required=True)
    p.add_argument("--name", type=str, default="final")
    p.add_argument("--sr", type=int, default=44100)
    # Changed: --mp3 deprecated in favor of --format
    p.add_argument("--mp3", type=int, default=0, help="deprecated")
    p.add_argument("--format", type=str, default="wav", help="wav, mp3, flac, ogg, m4a")
    return p.parse_args()

def get_next_version(out_dir: Path, prefix: str, ext: str) -> int:
    # Check existing files of target extension to increment version
    # Actually, we should check ALL versions to be safe? 
    # Usually we want same ID for same generated batch.
    # Let's check based on prefix regardless of extension?
    # Or just check global pattern {prefix}_{n}.*
    
    # We stick to old logic but relax extension check
    existing = list(out_dir.glob(f"{prefix}_*.*"))
    max_ver = 0
    for p in existing:
        try:
            stem = p.stem  # {prefix}_{n}
            parts = stem.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                ver = int(parts[1])
                if ver > max_ver:
                    max_ver = ver
        except ValueError:
            pass
    return max_ver + 1


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Determine format
    target_format = args.format.lower().replace(".", "")
    if target_format not in AUDIO_EXTS:
        print(f"[WARN] Unknown format '{target_format}', falling back to wav.")
        target_format = "wav"

    # Backward compatibility: if --mp3 1 is passed and --format is default(wav), force mp3
    if args.mp3 == 1 and target_format == "wav":
        target_format = "mp3"

    ver = get_next_version(out_dir, args.name, target_format)
    
    # We always render to WAV first (as intermediate or final)
    # If target is WAV, this is final.
    # If target is others, this is temp (or we keep it? User might want intermediate wav?)
    # Usually pipelines keep intermediate wav or overwrite. 
    # Let's save as `tmp.wav` or strict name if target is wav.

    if target_format == "wav":
        final_path = out_dir / f"{args.name}_{ver}.wav"
        temp_wav = final_path
    else:
        # Temp wav file
        final_path = out_dir / f"{args.name}_{ver}.{target_format}"
        temp_wav = out_dir / f"{args.name}_{ver}_temp.wav"

    render_wav_from_event_grid(
        grid_json_path=args.grid_json,
        event_grid_json_path=args.event_grid_json,
        sample_root=args.sample_root,
        out_wav=str(temp_wav),
        target_sr=int(args.sr),
    )
    
    # Convert if needed
    if target_format != "wav":
        try:
            export_as(str(temp_wav), target_format, str(final_path))
            print(f"[DONE] {target_format}: {final_path}")
            # Clean up temp wav? 
            # If user didn't ask for wav, maybe we delete temp.
            # But debugging is easier if we keep it. 
            # For now, let's DELETE temp to avoid clutter unless requested.
            # (User didn't specify behavior, but standard is to output only requested)
            temp_wav.unlink(missing_ok=True)
        except Exception as e:
            print(f"[ERROR] Export failed: {e}")
            # Keep temp wav if fail
            print(f"Saved intermediate wav: {temp_wav}")
    else:
        print(f"[DONE] wav: {final_path}")


if __name__ == "__main__":
    main()