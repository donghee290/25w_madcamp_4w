from __future__ import annotations
import argparse
from pathlib import Path

from stage9_render.render_wav import render_wav_from_event_grid
from stage9_render.export_mp3 import wav_to_mp3

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

def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wav_path = out_dir / f"{args.name}.wav"
    mp3_path = out_dir / f"{args.name}.mp3"

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