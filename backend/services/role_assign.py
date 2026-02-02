from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import random

from stage2_role_assignment.role_assigner import RoleAssigner
from stage2_role_assignment.pool.build_pools import build_pools
from pipeline.run_role_assignment import (
    load_yaml,
    build_assigner_config,
    list_audio_files,
)


def _sample_result_to_dict(sr) -> Dict[str, Any]:
    def _k(x):
        return x.value if hasattr(x, "value") else str(x)

    return {
        "sample_id": sr.sample_id,
        "filepath": sr.filepath,
        "role": _k(sr.role),
        "confidence": float(sr.scores.confidence),
        "p_rule": {_k(k): float(v) for k, v in sr.scores.rule.values.items()},
        "p_clap": {_k(k): float(v) for k, v in sr.scores.clap.values.items()},
        "p_final": {_k(k): float(v) for k, v in sr.scores.final.values.items()},
        "rule_raw": {_k(k): float(v) for k, v in (sr.rule_raw_scores or {}).items()},
        "clap_sim": {_k(k): float(v) for k, v in (sr.clap_similarities or {}).items()},
        "features": {
            "energy": sr.features.energy,
            "rms": sr.features.rms,
            "sharpness": sr.features.sharpness,
            "attack_time": sr.features.attack_time,
            "decay_time": sr.features.decay_time,
            "low_ratio": sr.features.low_ratio,
            "mid_ratio": sr.features.mid_ratio,
            "high_ratio": sr.features.high_ratio,
            "spectral_flatness": sr.features.spectral_flatness,
            "zero_crossing_rate": sr.features.zero_crossing_rate,
        },
    }


def _pools_to_json_with_features(pools) -> Dict[str, Any]:
    def pack(sr) -> Dict[str, Any]:
        return {
            "sample_id": sr.sample_id,
            "filepath": sr.filepath,
            "role": sr.role.value if hasattr(sr.role, "value") else str(sr.role),
            "confidence": float(sr.scores.confidence),
            "features": {
                "energy": float(sr.features.energy),
                "decay_time": float(sr.features.decay_time),
                "sharpness": float(sr.features.sharpness),
            },
        }

    return {
        "CORE_POOL": [pack(x) for x in pools.core],
        "ACCENT_POOL": [pack(x) for x in pools.accent],
        "MOTION_POOL": [pack(x) for x in pools.motion],
        "FILL_POOL": [pack(x) for x in pools.fill],
        "TEXTURE_POOL": [pack(x) for x in pools.texture],
        "counts": {
            "CORE": len(pools.core),
            "ACCENT": len(pools.accent),
            "MOTION": len(pools.motion),
            "FILL": len(pools.fill),
            "TEXTURE": len(pools.texture),
        },
    }


def assign_roles(
    input_dir: Path,
    config_path: Path,
    prompts_path: Path,
    limit: int = 0,
    seed: int = 42,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Run role assignment for audio files under input_dir.
    Returns: (pools_json, per_sample_debug)
    """
    cfg = load_yaml(str(config_path))
    prompts_yaml = load_yaml(str(prompts_path))
    if "ensemble" in prompts_yaml:
        cfg["prompts_ensemble"] = {
            "method": prompts_yaml["ensemble"].get("method", "mean"),
            "topk": prompts_yaml["ensemble"].get("topk", 3),
        }

    assigner_cfg, pool_cfg, _ = build_assigner_config(cfg, prompts_path=str(prompts_path))
    assigner = RoleAssigner(assigner_cfg)

    files = list_audio_files(str(input_dir))
    if not files:
        raise RuntimeError(f"No audio files found in: {input_dir}")

    rng = random.Random(seed)
    rng.shuffle(files)
    if limit and limit > 0:
        files = files[:limit]

    results = []
    for f in files:
        results.append(assigner.assign_file(f))

    pools = build_pools(results, pool_cfg)
    pools_json = _pools_to_json_with_features(pools)
    debug_list = [_sample_result_to_dict(x) for x in results]

    return pools_json, debug_list
