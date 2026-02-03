from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ..types import Role, RolePools, SampleResult


@dataclass
class PoolConfig:
    # Legacy config fields preserved to avoid breaking instantiation, 
    # but most won't be used in the new logic.
    required_roles: List[str]
    max_sizes: Dict[str, int]

    promote_when_missing_enabled: bool = True
    forbid_core_if_decay_long_threshold: float = 0.75
    forbid_core_if_flatness_threshold: float = 0.25
    forbid_motion_if_high_ratio_threshold: float = 0.25

    rebalance_when_excess_enabled: bool = True
    min_margin_keep: float = 0.08
    try_third_best_if_target_excess: bool = True


def build_pools(
    results: List[SampleResult],
    cfg: PoolConfig,
) -> RolePools:
    """
    Strict Assignment Logic:
    1. If total samples <= 3: Priority is CORE -> ACCENT -> MOTION.
    2. If total samples > 3: Priority is CORE -> ACCENT -> MOTION -> FILL -> TEXTURE.
    3. For each target role, pick the unassigned sample with the highest score for that role.
    4. Only ONE sample per role is assigned.
    5. Any remaining samples are dropped.
    """
    pools = RolePools()
    
    # 1. Determine Target Roles
    if len(results) <= 3:
        target_roles = [Role.CORE, Role.ACCENT, Role.MOTION]
    else:
        target_roles = [
            Role.CORE, 
            Role.ACCENT, 
            Role.MOTION, 
            Role.FILL, 
            Role.TEXTURE
        ]

    assigned_ids: Set[str] = set()

    for role in target_roles:
        # Filter out already assigned samples
        candidates = [r for r in results if r.sample_id not in assigned_ids]
        
        if not candidates:
            break

        # Find best candidate for this role
        # Sort by p_final[role] descending
        best_candidate = max(
            candidates, 
            key=lambda x: float(x.scores.final.values.get(role, -1.0))
        )

        # Assign
        best_candidate.role = role
        pools.get(role).append(best_candidate)
        assigned_ids.add(best_candidate.sample_id)

    return pools


def pools_to_json_dict(pools: RolePools) -> Dict:
    """
    최종 출력용 json dict
    """
    def pack(sr: SampleResult) -> Dict:
        return {
            "sample_id": sr.sample_id,
            "filepath": sr.filepath,
            "role": sr.role.value,
            "confidence": float(sr.scores.confidence),
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