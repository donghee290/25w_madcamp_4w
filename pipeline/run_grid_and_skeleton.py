# pipeline/run_grid_and_skeleton.py
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


from beat_grid.grid import GridConfig, build_grid
from beat_grid.patterns.skeleton import SkeletonConfig, build_skeleton_events


AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--pools_json", type=str, default="random", help="Path to pools json or 'random'")
    p.add_argument("--out_dir", type=str, required=True)

    p.add_argument("--bpm", type=float, required=True)
    p.add_argument("--bars", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)

    p.add_argument("--motion_mode", type=str, default="B")        # A/B
    p.add_argument("--motion_keep", type=int, default=6)          # 4~8
    p.add_argument("--fill_prob", type=float, default=0.25)
    p.add_argument("--texture", type=int, default=1)              # 1/0

    # render 관련 (필요하면 바꿔서 쓰세요)
    p.add_argument("--sample_root", type=str, default="examples/input_samples")
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


def _event_to_dict(e: Any) -> Dict[str, Any]:
    """
    events.py/skeleton.py 변경에도 최대한 안 깨지도록
    가능한 필드를 폭넓게 받아서 표준 event dict로 맞춥니다.
    """
    # dict로 이미 왔다면 우선 그대로 쓰되, 키 이름만 표준화
    if isinstance(e, dict):
        d = dict(e)
    elif is_dataclass(e):
        d = asdict(e)
    else:
        # 일반 객체: attribute 기반으로 뽑기
        d = {}
        for k in ["bar", "step", "role", "sample_id", "vel", "dur_steps", "micro_offset_ms", "source", "filepath"]:
            if hasattr(e, k):
                d[k] = getattr(e, k)

    # role enum/obj → str
    role = d.get("role", None)
    if role is not None and hasattr(role, "value"):
        try:
            d["role"] = role.value
        except Exception:
            d["role"] = str(role)

    # 필수 키 기본값
    d.setdefault("micro_offset_ms", 0.0)
    d.setdefault("source", "skeleton")

    # 타입 정리
    if "bar" in d:
        d["bar"] = int(d["bar"])
    if "step" in d:
        d["step"] = int(d["step"])
    if "vel" in d:
        d["vel"] = float(d["vel"])
    if "dur_steps" in d:
        d["dur_steps"] = int(d["dur_steps"])
    if "micro_offset_ms" in d:
        d["micro_offset_ms"] = float(d["micro_offset_ms"])

    # sample_id는 string으로
    if "sample_id" in d and d["sample_id"] is not None:
        d["sample_id"] = str(d["sample_id"])

    # filepath가 있으면 렌더가 더 편하지만, 없어도 render에서 sample_id로 lookup하게 둘 수 있음
    if "filepath" in d and d["filepath"] is not None:
        d["filepath"] = str(d["filepath"])

    # 최종 jsonable 정리
    return _jsonable(d)


def _select_pools_path(pools_path_str: str) -> Path:
    if not pools_path_str or pools_path_str.lower() == "random":
        candidates = list(Path("outs/outs_role").glob("role_pools_*.json"))
        if not candidates:
            candidates = list(Path(".").glob("role_pools_*.json"))
        if not candidates:
            raise RuntimeError("No 'role_pools_*.json' found for random selection.")
        import random
        selected_pool = random.choice(candidates)
        print(f"[INFO] Randomly selected pool: {selected_pool}")
        return selected_pool
    return Path(pools_path_str)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pools_path = _select_pools_path(args.pools_json)
    pools: Dict[str, Any] = json.loads(pools_path.read_text(encoding="utf-8"))

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

    # 2) skeleton events
    scfg = SkeletonConfig(
        seed=int(args.seed),
        steps_per_bar=16,
        num_bars=int(args.bars),
        motion_mode=str(args.motion_mode),
        motion_keep_per_bar=int(args.motion_keep),
        fill_prob=float(args.fill_prob),
        texture_enabled=bool(int(args.texture)),
    )

    events, chosen = build_skeleton_events(
        pools, 
        scfg, 
        tstep=grid.tstep  # Pass float value for decay calculation
    )

    # events 직렬화 (변경된 events.py/skeleton.py를 최대한 흡수)
    events_json: List[Dict[str, Any]] = [_event_to_dict(e) for e in events]

    # 3) output numbering
    ver = get_next_version(out_dir)

    base_grid = out_dir / f"grid_{ver}.json"
    base_events = out_dir / f"event_grid_{ver}.json"
    base_meta = out_dir / f"skeleton_meta_{ver}.json"
    base_wav = out_dir / f"render_{ver}.wav"

    base_grid.write_text(json.dumps(grid_json, ensure_ascii=False, indent=2), encoding="utf-8")
    base_events.write_text(json.dumps(events_json, ensure_ascii=False, indent=2), encoding="utf-8")
    base_meta.write_text(
        json.dumps({"chosen_samples": _jsonable(chosen)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[DONE] grid + skeleton created")
    print(f" - ID: {ver}")
    print(" - pools:", str(pools_path))
    print(" - grid:", str(base_grid))
    print(" - events:", str(base_events))
    print(" - meta:", str(base_meta))
    print(" - num_events:", len(events_json))

    # 4) render
    try:
        from beat_grid.test_audio_render.render import render_events

        sample_root = Path(args.sample_root)
        print(f"[INFO] Rendering audio to {base_wav} ...")
        print(f"[INFO] sample_root: {sample_root}")

        render_events(
            grid_json=grid_json,
            events=events_json,
            sample_root=sample_root,
            out_wav=base_wav,
            target_sr=int(args.render_sr),
        )
        print("[DONE] audio rendered:", str(base_wav))
    except ImportError:
        print("[WARN] Could not import beat_grid.test_audio_render.render. Audio not generated.")
    except Exception as e:
        print(f"[ERROR] Audio rendering failed: {e}")


if __name__ == "__main__":
    main()