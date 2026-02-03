from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from stage5_note_and_midi.grid_io import load_grid_json, dump_grid_json
from stage5_note_and_midi.pools_io import load_pools_json
from stage5_note_and_midi.sample_select import SampleSelector, SampleSelectorConfig
from stage5_note_and_midi.normalize import load_note_list_json, normalize_notes_to_event_grid, dump_event_grid
from stage5_note_and_midi.midi_export import export_event_grid_to_midi
from stage5_note_and_midi.progressive import ProgressiveConfig, build_progressive_timeline


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
    p.add_argument("--progressive", type=int, default=0)
    p.add_argument("--segment_bars", type=int, default=4)
    p.add_argument("--layers", type=str, default="CORE,ACCENT,MOTION,FILL")  # comma sep

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

    events = normalize_notes_to_event_grid(
        grid=grid,
        notes=notes,
        selector=selector,
        source="model",
        clamp_ms=float(args.clamp_ms),
    )

    ver = get_next_version(out_dir, prefix="event_grid")
    event_path = out_dir / f"event_grid_{ver}.json"
    midi_path = out_dir / f"notes_{ver}.mid"
    meta_path = out_dir / f"note_meta_{ver}.json"

    event_path.write_text(json.dumps(dump_event_grid(events), ensure_ascii=False, indent=2), encoding="utf-8")
    export_event_grid_to_midi(grid, events, midi_path)

    meta = {
        "version": ver,
        "grid_json": str(Path(args.grid_json)),
        "notes_json": str(Path(args.notes_json)),
        "pools_json": str(Path(args.pools_json)),
        "seed": int(args.seed),
        "selector_mode": str(args.selector_mode),
        "clamp_ms": float(args.clamp_ms),
        "num_events": len(events),
        "progressive": bool(int(args.progressive)),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[DONE] stage6 note + midi")
    print(" - event_grid:", str(event_path))
    print(" - midi:", str(midi_path))
    print(" - meta:", str(meta_path))
    print(" - num_events:", len(events))

    if int(args.progressive) == 1:
        layers = tuple([x.strip().upper() for x in str(args.layers).split(",") if x.strip()])
        pcfg = ProgressiveConfig(segment_bars=int(args.segment_bars), layers=layers)
        new_grid, prog_events, prog_meta = build_progressive_timeline(grid, events, pcfg)

        ver2 = get_next_version(out_dir, prefix="event_grid_progressive")
        grid2_path = out_dir / f"grid_progressive_{ver2}.json"
        event2_path = out_dir / f"event_grid_progressive_{ver2}.json"
        midi2_path = out_dir / f"notes_progressive_{ver2}.mid"
        meta2_path = out_dir / f"note_progressive_meta_{ver2}.json"

        grid2_path.write_text(json.dumps(dump_grid_json(new_grid), ensure_ascii=False, indent=2), encoding="utf-8")
        event2_path.write_text(json.dumps(dump_event_grid(prog_events), ensure_ascii=False, indent=2), encoding="utf-8")
        export_event_grid_to_midi(new_grid, prog_events, midi2_path)

        meta2 = {"version": ver2, "progressive": prog_meta, "num_events": len(prog_events)}
        meta2_path.write_text(json.dumps(meta2, ensure_ascii=False, indent=2), encoding="utf-8")

        print("[DONE] progressive layered output")
        print(" - grid:", str(grid2_path))
        print(" - event_grid:", str(event2_path))
        print(" - midi:", str(midi2_path))
        print(" - meta:", str(meta2_path))
        print(" - total_bars:", new_grid.num_bars)
        print(" - num_events:", len(prog_events))


if __name__ == "__main__":
    main()