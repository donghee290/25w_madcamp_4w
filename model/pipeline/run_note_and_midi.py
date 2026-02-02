from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from stage4_model_gen.groovae.postprocess import (
    load_json,
    save_json,
    load_midi_as_notes,
    build_events_from_notes,
    apply_poly_limit_and_protect,
    assign_samples_from_pools,
    build_progressive_arrangement,
    export_midi_from_events,
    deduce_sample_root_from_pools,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()

    p.add_argument("--grid_json", type=str, required=True)
    p.add_argument("--events_json", type=str, required=True)
    p.add_argument("--pools_json", type=str, required=True)
    p.add_argument("--groovae_midi", type=str, required=True)

    p.add_argument("--out_dir", type=str, required=True)
    p.add_argument("--id", type=int, default=0, help="0이면 auto numbering, 아니면 지정")

    # 6-1: 스냅 강도(여긴 MVP라 step 스냅 고정, micro_offset_ms 저장)
    p.add_argument("--max_poly", type=int, default=3)

    # 6-2: MIDI export
    p.add_argument("--export_midi", type=int, default=1)  # 1/0

    # 6-3: progressive arrangement
    p.add_argument("--arrangement", type=str, default="progressive", choices=["none", "progressive"])
    p.add_argument("--stage_bars", type=int, default=4)

    # render (선택)
    p.add_argument("--render", type=int, default=0)  # 1/0
    p.add_argument("--target_sr", type=int, default=44100)

    return p.parse_args()


def get_next_version(out_dir: Path) -> int:
    existing = list(out_dir.glob("event_grid_*.json"))
    max_ver = 0
    for p in existing:
        stem = p.stem  # event_grid_{n}
        parts = stem.split("_")
        if parts and parts[-1].isdigit():
            max_ver = max(max_ver, int(parts[-1]))
    return max_ver + 1


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ver = int(args.id) if int(args.id) > 0 else get_next_version(out_dir)

    grid_json: Dict[str, Any] = load_json(args.grid_json)
    base_events: List[Dict[str, Any]] = load_json(args.events_json)
    pools: Dict[str, Any] = load_json(args.pools_json)

    # 1) GrooVAE MIDI 읽기
    notes = load_midi_as_notes(args.groovae_midi)

    # 2) MIDI notes -> events (UI 스냅 + micro_offset_ms 유지)
    events = build_events_from_notes(
        grid_json=grid_json,
        notes=notes,
        source_tag="groovae",
    )

    # 3) poly limit + CORE/ACCENT 보호 규칙 적용
    events = apply_poly_limit_and_protect(
        events=events,
        max_poly=int(args.max_poly),
        protect_core_steps={0, 4, 8, 12},
        protect_accent_steps={4, 12},
    )

    # 4) sample_id 부여 (pools 기반, role별 고정/round-robin)
    events = assign_samples_from_pools(
        events=events,
        pools=pools,
        seed=int(grid_json.get("seed", 42)) if "seed" in grid_json else 42,
    )

    # 5) 표준 event_grid.json 저장
    event_path = out_dir / f"event_grid_{ver}.json"
    grid_path = out_dir / f"grid_{ver}.json"
    save_json(event_path, events)
    save_json(grid_path, grid_json)

    print("[DONE] 6-1 event_grid generated")
    print(" - grid:", grid_path)
    print(" - events:", event_path)
    print(" - num_events:", len(events))

    # 6) MIDI export (events -> midi)
    if int(args.export_midi) == 1:
        midi_path = out_dir / f"event_grid_{ver}.mid"
        export_midi_from_events(
            grid_json=grid_json,
            events=events,
            out_midi=midi_path,
        )
        print("[DONE] 6-2 MIDI exported:", midi_path)

    # 7) progressive arrangement
    if args.arrangement == "progressive":
        stage_bars = int(args.stage_bars)

        stages = [
            (stage_bars, ("CORE",)),
            (stage_bars, ("CORE", "ACCENT")),
            (stage_bars, ("CORE", "ACCENT", "MOTION")),
            (stage_bars, ("CORE", "ACCENT", "MOTION", "FILL")),
            (stage_bars, ("CORE", "ACCENT", "MOTION", "FILL", "TEXTURE")),
        ]

        grid_prog, events_prog = build_progressive_arrangement(
            base_grid=grid_json,
            base_events=events,
            stages=stages,
        )

        grid_prog_path = out_dir / f"grid_progressive_{ver}.json"
        events_prog_path = out_dir / f"event_grid_progressive_{ver}.json"
        save_json(grid_prog_path, grid_prog)
        save_json(events_prog_path, events_prog)

        print("[DONE] 6-3 progressive created")
        print(" - grid_progressive:", grid_prog_path)
        print(" - events_progressive:", events_prog_path)
        print(" - total_bars:", grid_prog["num_bars"])
        print(" - num_events:", len(events_prog))

        if int(args.export_midi) == 1:
            midi_prog_path = out_dir / f"event_grid_progressive_{ver}.mid"
            export_midi_from_events(grid_prog, events_prog, midi_prog_path)
            print("[DONE] progressive MIDI exported:", midi_prog_path)

        # render (optional)
        if int(args.render) == 1:
            try:
                from stage3_beat_grid.test_audio_render.render import render_events
            except Exception:
                from stage3_beat_grid.test_audio_render.render import render_events  # fallback

            sample_root = deduce_sample_root_from_pools(pools) or Path("examples/input_samples")
            wav_path = out_dir / f"render_progressive_{ver}.wav"
            print("[INFO] Rendering progressive wav:", wav_path)
            render_events(
                grid_json=grid_prog,
                events=events_prog,
                sample_root=sample_root,
                out_wav=wav_path,
                target_sr=int(args.target_sr),
            )
            print("[DONE] progressive render:", wav_path)

    else:
        # render non-progressive (optional)
        if int(args.render) == 1:
            try:
                from stage3_beat_grid.test_audio_render.render import render_events
            except Exception:
                from stage3_beat_grid.test_audio_render.render import render_events  # fallback

            sample_root = deduce_sample_root_from_pools(pools) or Path("examples/input_samples")
            wav_path = out_dir / f"render_{ver}.wav"
            print("[INFO] Rendering wav:", wav_path)
            render_events(
                grid_json=grid_json,
                events=events,
                sample_root=sample_root,
                out_wav=wav_path,
                target_sr=int(args.target_sr),
            )
            print("[DONE] render:", wav_path)


if __name__ == "__main__":
    main()