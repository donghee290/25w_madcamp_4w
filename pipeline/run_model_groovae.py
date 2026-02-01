# pipeline/run_model_groovae.py
from __future__ import annotations

import argparse, json
from pathlib import Path

from stage4_model_gen.groovae.to_noteseq import events_to_notesequence
from stage4_model_gen.groovae.runner import GrooVAERunner
from stage4_model_gen.groovae.postprocess import quantize_and_filter
from stage4_model_gen.groovae.from_noteseq import noteseq_to_events
from stage3_beat_grid.test_audio_render.render import render_events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid_json", required=True)
    ap.add_argument("--events_json", required=True)
    ap.add_argument("--pools_json", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--render", action="store_true", help="Enable audio rendering")
    ap.add_argument("--sample_root", default="examples/input_samples")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grid = json.loads(Path(args.grid_json).read_text())
    events = json.loads(Path(args.events_json).read_text())
    pools = json.loads(Path(args.pools_json).read_text())

    ns_in = events_to_notesequence(grid, events)
    runner = GrooVAERunner(seed=args.seed)
    ns_out = runner.run(ns_in)
    ns_post = quantize_and_filter(ns_out, grid)

    sample_map = {k.replace("_POOL", ""): v for k, v in pools.items() if k.endswith("_POOL")}
    events_out = noteseq_to_events(ns_post, grid, sample_map)

    vid = len(list(out_dir.glob("event_grid_groovae_*.json"))) + 1
    out_events = out_dir / f"event_grid_groovae_{vid}.json"
    out_wav = out_dir / f"render_groovae_{vid}.wav"

    out_events.write_text(json.dumps(events_out, indent=2, ensure_ascii=False))

    if args.render:
        render_events(
            grid_json=grid,
            events=events_out,
            sample_root=Path(args.sample_root),
            out_wav=out_wav,
            target_sr=44100,
        )

    print("[DONE] GrooVAE stage complete")
    print(" - events:", out_events)
    print(" - wav:", out_wav)


if __name__ == "__main__":
    main()