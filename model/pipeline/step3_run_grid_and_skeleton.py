# pipeline/run_grid_and_skeleton.py
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List

import sys
# Add model dir to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from stage3_beat_grid.grid import GridConfig, build_grid
from stage3_beat_grid.patterns.skeleton import SkeletonConfig, build_skeleton_events

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    
    p.add_argument("--out_dir", type=str, required=True)
    p.add_argument("--bpm", type=float, required=True)
    p.add_argument("--bars", type=int, default=4)
    
    # Restored Skeleton Inputs
    p.add_argument("--style", type=str, default="rock", help="Music style for skeleton (rock, hiphop, house, etc)")
    p.add_argument("--pools_json", type=str, required=False, help="Path to pools.json (required for sample selection)")
    p.add_argument("--seed", type=int, default=42)

    # Render config (optional, maybe unused now if we don't render here)
    p.add_argument("--render_sr", type=int, default=44100)

    return p.parse_args()


def get_next_version(out_dir: Path) -> int:
    existing = list(out_dir.glob("grid_*.json"))
    max_ver = 0
    for p in existing:
        try:
            stem = p.stem  # grid_{n}
            parts = stem.split("_")
            if len(parts) >= 2 and parts[-1].isdigit():
                ver = int(parts[-1])
                if ver > max_ver:
                    max_ver = ver
        except ValueError:
            pass
    return max_ver + 1


def _jsonable(obj: Any) -> Any:
    """
    dataclass / enum / Path / numpy scalar 등 안전 변환
    """
    if obj is None:
        return None

    # dataclass
    if is_dataclass(obj):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}

    # dict
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}

    # list/tuple
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]

    # Path
    if isinstance(obj, Path):
        return str(obj)

    # Enum (role 같은 것)
    if hasattr(obj, "value"):
        try:
            return _jsonable(obj.value)
        except Exception:
            return str(obj)

    # numpy scalar 등
    try:
        import numpy as np  # type: ignore
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
    except Exception:
        pass

    # 기본
    return obj


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) grid
    gcfg = GridConfig(
        bpm=float(args.bpm),
        num_bars=int(args.bars),
        steps_per_bar=16,
        meter_numer=4,
        meter_denom=4,
    )
    grid = build_grid(gcfg)

    grid_json = {
        "bpm": float(grid.cfg.bpm),
        "meter": f"{int(grid.cfg.meter_numer)}/{int(grid.cfg.meter_denom)}",
        "steps_per_bar": int(grid.cfg.steps_per_bar),
        "num_bars": int(grid.cfg.num_bars),
        "tbeat": float(grid.tbeat),
        "tbar": float(grid.tbar),
        "tstep": float(grid.tstep),
        "bar_start": _jsonable(grid.bar_start),
        "t_step": _jsonable(grid.t_step),
    }

    # 2) Skeleton Generation (Constraint)
    pools = {}
    if args.pools_json and Path(args.pools_json).exists():
        pools = json.loads(Path(args.pools_json).read_text())
    
    # Default configs for now
    scfg = SkeletonConfig(
        seed=args.seed,
        steps_per_bar=16,
        num_bars=int(args.bars),
        pattern_style=args.style,
        fill_prob=1.0,  # Force fill generation (User Requirement: 100%) 
        texture_enabled=True
    )
    
    # Generate Reference Skeleton
    # This logic creates the "Standard" pattern for the requested style
    skel_events, chosen = build_skeleton_events(pools, scfg, tstep=grid.tstep)
    
    # 3) Output numbering
    ver = get_next_version(out_dir)

    base_grid = out_dir / f"grid_{ver}.json"
    skel_out = out_dir / f"skeleton_{ver}.json"
    
    # Write Grid
    base_grid.write_text(json.dumps(grid_json, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Write Skeleton (as Reference)
    # We convert Event objects to list of dicts
    skel_json = [_jsonable(e) for e in skel_events]
    skel_out.write_text(json.dumps(skel_json, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[DONE] Grid & Skeleton setup complete")
    print(f" - ID: {ver}")
    print(" - grid:", str(base_grid))
    print(" - skeleton:", str(skel_out))
    print(" - chosen:", chosen)

if __name__ == "__main__":
    main()