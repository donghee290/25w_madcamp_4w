from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..types import Role, RolePools, SampleResult


@dataclass
class PoolConfig:
    required_roles: List[str]  # ["CORE","ACCENT","MOTION"]

    max_sizes: Dict[str, int]  # {"CORE":4, "ACCENT":4, "MOTION":10}

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
    SampleResult 리스트를 받아 역할별 pool을 만들고,
    1) 필수 pool 비어있으면 승격(promote)
    2) CORE/ACCENT/MOTION 과다면 재배치(rebalance)
    를 수행합니다.
    """
    pools = RolePools()
    _initial_fill(pools, results)

    if cfg.promote_when_missing_enabled:
        _promote_missing_required(pools, results, cfg)

    if cfg.rebalance_when_excess_enabled:
        _rebalance_excess(pools, cfg)

    return pools


def pools_to_json_dict(pools: RolePools) -> Dict:
    """
    최종 출력용 json dict
    - SampleResult 전체를 다 넣기보다, pipeline에서 쓰는 핵심만 넣음
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


# =========================
# Internal
# =========================

def _initial_fill(pools: RolePools, results: List[SampleResult]) -> None:
    for r in results:
        pools.get(r.role).append(r)


def _required_roles(cfg: PoolConfig) -> List[Role]:
    out: List[Role] = []
    for s in cfg.required_roles:
        out.append(Role(s))
    return out


def _is_forbidden_promote(role: Role, r: SampleResult, cfg: PoolConfig) -> bool:
    f = r.features

    if role == Role.CORE:
        # 너무 지속적 + 노이즈면 CORE 승격 금지
        if (f.decay_time >= cfg.forbid_core_if_decay_long_threshold) and (
            f.spectral_flatness >= cfg.forbid_core_if_flatness_threshold
        ):
            return True

    if role == Role.MOTION:
        # 고역 비율 너무 낮으면 MOTION 승격 금지
        if f.high_ratio <= cfg.forbid_motion_if_high_ratio_threshold:
            return True

    return False


def _promote_missing_required(pools: RolePools, results: List[SampleResult], cfg: PoolConfig) -> None:
    """
    필수 role pool이 비어있으면, 그 role 확률이 높은 샘플을 승격
    (현재 role이 무엇이든 상관없이 이동)
    """
    required = _required_roles(cfg)

    for need_role in required:
        if len(pools.get(need_role)) > 0:
            continue

        # 후보: p_final[need_role]가 큰 순
        candidates = sorted(
            results,
            key=lambda x: float(x.scores.final.values.get(need_role, 0.0)),
            reverse=True,
        )

        promoted = None
        for cand in candidates:
            if _is_forbidden_promote(need_role, cand, cfg):
                continue
            promoted = cand
            break

        if promoted is None:
            # 금지 조건 때문에 못 찾으면 그냥 최고 확률을 강제로 승격
            promoted = candidates[0] if candidates else None

        if promoted is None:
            continue

        # 기존 pool에서 제거 후 새 role pool로 이동
        _move_sample(pools, promoted, need_role)


def _rebalance_excess(pools: RolePools, cfg: PoolConfig) -> None:
    """
    CORE/ACCENT/MOTION 과다하면 margin 낮은 것부터 재배치
    규칙:
      - 초과분은 confidence(margin) 낮은 샘플부터 이동
      - 이동 대상은 2등 role 우선
      - 대상 role도 과다면 3등 role 시도(옵션)
      - 이동 후 필수 3개 pool이 깨지면 금지
    """
    limits: Dict[Role, int] = {}
    for k, v in cfg.max_sizes.items():
        limits[Role(k)] = int(v)

    # 필수 role 집합
    required_set = set(_required_roles(cfg))

    # 초과 role 순회
    for role, limit in limits.items():
        pool = pools.get(role)
        if len(pool) <= limit:
            continue

        # confidence 낮은 것부터 이동 후보
        # (낮을수록 애매, 이동시키기 적합)
        pool_sorted = sorted(pool, key=lambda x: float(x.scores.confidence))

        # 초과 개수만큼 이동
        excess = len(pool) - limit
        moved = 0

        for sr in pool_sorted:
            if moved >= excess:
                break

            # 필수 role이 1개만 남으면 못 빼게
            if role in required_set and len(pools.get(role)) <= 1:
                continue

            # alt role 선택: 2등(또는 3등)
            target = _choose_alternative_role(sr, current=role, pools=pools, limits=limits, cfg=cfg)

            if target is None:
                continue

            # 이동이 필수 pool을 깨지 않는지 체크
            if role in required_set and len(pools.get(role)) <= 1:
                continue

            _move_sample(pools, sr, target)
            moved += 1


def _choose_alternative_role(
    sr: SampleResult,
    current: Role,
    pools: RolePools,
    limits: Dict[Role, int],
    cfg: PoolConfig,
) -> Optional[Role]:
    """
    p_final 기반으로 current 제외하고 높은 순으로 후보 선택.
    - target이 과다면(한도가 있는 경우) 3등 시도(옵션)
    - 너무 애매한 건(TEXTURE 흡수)로 보내도 됨
    """
    sorted_roles = sr.scores.final.sorted()  # [(role, prob), ...]

    # 후보 리스트: current 제외
    candidates: List[Role] = [r for (r, _) in sorted_roles if r != current]

    def is_excess(role: Role) -> bool:
        if role not in limits:
            return False  # 제한 없는 role(FILL/TEXTURE)은 과다 판정 안 함
        return len(pools.get(role)) > limits[role]

    # 2등 우선
    if not candidates:
        return None

    first = candidates[0]
    if not is_excess(first):
        return first

    if cfg.try_third_best_if_target_excess and len(candidates) >= 2:
        second = candidates[1]
        if not is_excess(second):
            return second

    # 그래도 안되면 TEXTURE로 흡수(안전)
    return Role.TEXTURE


def _move_sample(pools: RolePools, sr: SampleResult, new_role: Role) -> None:
    """
    sr을 현재 역할 pool에서 제거하고 new_role pool로 이동
    (sr.role도 업데이트)
    """
    old_role = sr.role
    if old_role == new_role:
        return

    old_pool = pools.get(old_role)
    try:
        old_pool.remove(sr)
    except ValueError:
        pass

    sr.role = new_role
    pools.get(new_role).append(sr)