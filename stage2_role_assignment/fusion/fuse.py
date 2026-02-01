from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ..types import DSPFeatures, Role, ScoreBundle, ScoreVector
from .guards import GuardsConfig, apply_guards


@dataclass
class FusionConfig:
    # p_final = alpha * p_rule + (1-alpha) * p_clap
    alpha: float = 0.65

    # (선택) 최종 확률에 role bias를 더하는 방식(확률 공간에서 곱셈에 가까운 효과)
    # 예: TEXTURE 쏠림이면 TEXTURE bias를 -0.05로 둔 상태를 활용 가능
    # 여기서는 "확률값에 더한 뒤 clamp"로 간단히 처리
    role_bias: Optional[Dict[str, float]] = None

    confidence_margin_threshold: float = 0.12

    guards: GuardsConfig = field(default_factory=GuardsConfig)


def fuse_rule_and_clap(
    p_rule: ScoreVector,
    p_clap: ScoreVector,
    features: DSPFeatures,
    cfg: FusionConfig,
) -> Tuple[ScoreVector, float]:
    """
    p_rule + p_clap 결합 후 가드레일 적용.
    returns:
      - p_final (normalized)
      - confidence margin (max - second)
    """
    alpha = float(cfg.alpha)
    alpha = 0.0 if alpha < 0.0 else (1.0 if alpha > 1.0 else alpha)

    final_vals: Dict[Role, float] = {}

    for role in Role.list():
        pr = float(p_rule.values.get(role, 0.0))
        pc = float(p_clap.values.get(role, 0.0))
        final_vals[role] = alpha * pr + (1.0 - alpha) * pc

    # role bias(선택)
    if cfg.role_bias:
        for r in Role.list():
            b = float(cfg.role_bias.get(r.value, 0.0))
            final_vals[r] = float(final_vals[r] + b)

    # clamp: 음수 방지
    for r in final_vals:
        if final_vals[r] < 0.0:
            final_vals[r] = 0.0

    p_final = ScoreVector(values=final_vals).normalize()

    # 1차 confidence
    margin = p_final.margin()

    # guards는 margin을 참고하므로 margin 전달
    if cfg.guards and cfg.guards.enabled:
        p_final = apply_guards(p_final, features, cfg.guards, confidence_margin=margin)
        margin = p_final.margin()

    return p_final, float(margin)


def build_score_bundle(
    p_rule: ScoreVector,
    p_clap: ScoreVector,
    p_final: ScoreVector,
) -> ScoreBundle:
    """
    SampleResult에 넣기 위한 ScoreBundle 생성.
    """
    conf = p_final.margin()
    return ScoreBundle(rule=p_rule, clap=p_clap, final=p_final, confidence=float(conf))