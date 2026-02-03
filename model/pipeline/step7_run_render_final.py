from __future__ import annotations
import argparse
from pathlib import Path

import sys
# Add model dir to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from stage7_render.render_wav import render_wav_from_event_grid
from stage7_render.export_mp3 import wav_to_mp3

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--grid_json", type=str, required=True)
    p.add_argument("--event_grid_json", type=str, required=True)
    p.add_argument("--sample_root", type=str, default="examples/input_samples")
    p.add_argument("--out_dir", type=str, required=True)
    p.add_argument("--name", type=str, default="final")
    p.add_argument("--sr", type=int, default=44100)
    p.add_argument("--mp3", type=int, default=1)
    return p.parse_args()

def get_next_version(out_dir: Path, prefix: str) -> int:
    existing = list(out_dir.glob(f"{prefix}_*.wav"))
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

    ver = get_next_version(out_dir, args.name)
    wav_path = out_dir / f"{args.name}_{ver}.wav"
    mp3_path = out_dir / f"{args.name}_{ver}.mp3"

    render_wav_from_event_grid(
        grid_json_path=args.grid_json,
        event_grid_json_path=args.event_grid_json,
        sample_root=args.sample_root,
        out_wav=str(wav_path),
        target_sr=int(args.sr),
    )
    print("[DONE] wav:", str(wav_path))

    if int(args.mp3) == 1:
        wav_to_mp3(str(wav_path), str(mp3_path))
        print("[DONE] mp3:", str(mp3_path))

if __name__ == "__main__":
    main()