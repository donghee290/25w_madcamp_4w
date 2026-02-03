from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import sys
# Add model dir to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from stage5_note_gen.grid_io import load_grid_json, dump_grid_json
from stage5_note_gen.pools_io import load_pools_json
from stage5_note_gen.sample_select import SampleSelector, SampleSelectorConfig
from stage5_note_gen.normalize import load_note_list_json, normalize_notes_to_event_grid, dump_event_grid
from stage5_note_gen.midi_export import export_event_grid_to_midi
from stage5_note_gen.progressive import ProgressiveConfig, build_progressive_timeline


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()

    p.add_argument("--grid_json", type=str, required=True)
    p.add_argument("--notes_json", type=str, required=True, help="stage4 output notes list json (start/end/pitch/velocity/role/...)")
    p.add_argument("--pools_json", type=str, required=True)
    p.add_argument("--out_dir", type=str, required=True)

    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--selector_mode", type=str, default="round_robin", choices=["round_robin", "fixed", "random"])

    p.add_argument("--clamp_ms", type=float, default=40.0)

    # progressive (core-only 4 bars -> +accent 4 bars -> ...)
    p.add_argument("--progressive", type=int, default=1, help="If 1, generates full song structure using progressive layering")
    p.add_argument("--segment_bars", type=int, default=4)
    p.add_argument("--layers", type=str, default="CORE,ACCENT,MOTION,FILL")  # comma sep
    p.add_argument("--repeat_full", type=int, default=4, help="Number of times to repeat the final full section")

    return p.parse_args()


def get_next_version(out_dir: Path, prefix: str) -> int:
    existing = list(out_dir.glob(f"{prefix}_*.json"))
    max_ver = 0
    for p in existing:
        stem = p.stem
        parts = stem.split("_")
        if parts and parts[-1].isdigit():
            max_ver = max(max_ver, int(parts[-1]))
    return max_ver + 1


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grid = load_grid_json(args.grid_json)
    pools = load_pools_json(args.pools_json)
    notes = load_note_list_json(args.notes_json)

    selector = SampleSelector(
        pools=pools,
        cfg=SampleSelectorConfig(
            seed=int(args.seed),
            mode=str(args.selector_mode),
            fixed_per_role=(args.selector_mode == "fixed"),
        ),
    )

    base_loop_events = normalize_notes_to_event_grid(
        grid=grid,
        notes=notes,
        selector=selector,
        source="model",
        clamp_ms=float(args.clamp_ms),
    )

    # If progressive is ON (default), we build the full song structure
    # and use THAT as the main output.
    if int(args.progressive) == 1:
        print("[INFO] Building progressive song structure...")
        layers = tuple([x.strip().upper() for x in str(args.layers).split(",") if x.strip()])
        pcfg = ProgressiveConfig(
            segment_bars=int(args.segment_bars), 
            layers=layers,
            final_repeat=int(args.repeat_full)
        )
        final_grid, final_events, final_meta = build_progressive_timeline(grid, base_loop_events, pcfg)
        
        # We also save the base loop for reference
        loop_ver = get_next_version(out_dir, prefix="event_grid_loop")
        out_dir.joinpath(f"event_grid_loop_{loop_ver}.json").write_text(
            json.dumps(dump_event_grid(base_loop_events), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        # If disabled, final output is just the base loop
        print("[INFO] progressive=0, outputting 4-bar loop only.")
        final_grid = grid
        final_events = base_loop_events
        final_meta = {"progressive": False}

    # Generate version for MAIN output
    ver = get_next_version(out_dir, prefix="event_grid")
    event_path = out_dir / f"event_grid_{ver}.json"
    midi_path = out_dir / f"notes_{ver}.mid"
    meta_path = out_dir / f"note_meta_{ver}.json"

    # Save MAIN output
    event_path.write_text(json.dumps(dump_event_grid(final_events), ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Also save the GRID logic (which might be expanded)
    grid_path = out_dir / f"grid_{ver}.json"
    grid_path.write_text(json.dumps(dump_grid_json(final_grid), ensure_ascii=False, indent=2), encoding="utf-8")
    
    export_event_grid_to_midi(final_grid, final_events, midi_path)

    base_meta_info = {
        "version": ver,
        "grid_json": str(grid_path),
        "input_grid_json": str(Path(args.grid_json)),
        "notes_json": str(Path(args.notes_json)),
        "pools_json": str(Path(args.pools_json)),
        "seed": int(args.seed),
        "selector_mode": str(args.selector_mode),
        "clamp_ms": float(args.clamp_ms),
        "num_events": len(final_events),
        "progressive_info": final_meta,
    }
    meta_path.write_text(json.dumps(base_meta_info, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[DONE] stage5 finished")
    print(" - grid:", str(grid_path))
    print(" - event_grid:", str(event_path))
    print(" - midi:", str(midi_path))
    print(" - meta:", str(meta_path))
    print(" - total_bars:", final_grid.num_bars)
    print(" - num_events:", len(final_events))


if __name__ == "__main__":
    main()