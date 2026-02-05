from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..types import DSPFeatures, Role, ScoreVector


@dataclass
class TextureSuppressConfig:
    transient_S_threshold: float = 0.95
    decay_short_threshold: float = 0.05
    multiply: float = 0.90


@dataclass
class SustainedNoiseSuppressConfig:
    decay_long_threshold: float = 1.0
    flatness_threshold: float = 0.60
    core_multiply: float = 0.90
    accent_multiply: float = 0.90


@dataclass
class MotionMinConditionConfig:
    high_ratio_threshold: float = 0.05
    decay_max_threshold: float = 2.0
    multiply: float = 0.90


@dataclass
class FillConservativeConfig:
    min_prob: float = 0.10
    min_margin: float = 0.01
    multiply: float = 0.90


@dataclass
class LowConfTextureExtraSuppressConfig:
    enabled: bool = False
    margin_threshold: float = 0.10
    multiply: float = 0.80
    percussive_roles: List[str] = None

    def __post_init__(self):
        if self.percussive_roles is None:
            self.percussive_roles = ["CORE", "ACCENT", "MOTION", "FILL"]


@dataclass
class GuardsConfig:
    enabled: bool = True
    texture_suppress: TextureSuppressConfig = field(default_factory=TextureSuppressConfig)
    sustained_noise_suppress: SustainedNoiseSuppressConfig = field(default_factory=SustainedNoiseSuppressConfig)
    motion_min_condition: MotionMinConditionConfig = field(default_factory=MotionMinConditionConfig)
    fill_conservative: FillConservativeConfig = field(default_factory=FillConservativeConfig)
    low_conf_texture_extra_suppress: LowConfTextureExtraSuppressConfig = field(default_factory=LowConfTextureExtraSuppressConfig)


def apply_guards(
    probs: ScoreVector,
    features: DSPFeatures,
    cfg: GuardsConfig,
    confidence_margin: Optional[float] = None,
) -> ScoreVector:
    """
    p_final(또는 결합 직후 확률)에 가드레일을 적용해 안정화합니다.
    - probs는 role->prob 형태라고 가정하지만, 곱셈 후 normalize로 다시 확률화합니다.
    """
    if not cfg.enabled:
        return probs

    out = probs.clone()

    _guard_texture_suppress(out, features, cfg.texture_suppress)
    _guard_sustained_noise_suppress(out, features, cfg.sustained_noise_suppress)
    _guard_motion_min_condition(out, features, cfg.motion_min_condition)

    # fill 보수화는 confidence를 활용하면 더 안정적
    if confidence_margin is not None:
        _guard_fill_conservative(out, confidence_margin, cfg.fill_conservative)

    # conf 낮고 texture가 1등이면 추가 억제
    if confidence_margin is not None:
        _guard_low_conf_texture_extra(out, confidence_margin, cfg.low_conf_texture_extra_suppress)

    return out.normalize()


def _mul(out: ScoreVector, role: Role, m: float) -> None:
    if role in out.values:
        out.values[role] = float(out.values[role] * m)


def _guard_texture_suppress(out: ScoreVector, f: DSPFeatures, c: TextureSuppressConfig) -> None:
    # 타격성 강하고 decay 짧으면 texture 억제
    if (f.sharpness >= c.transient_S_threshold) and (f.decay_time <= c.decay_short_threshold):
        _mul(out, Role.TEXTURE, c.multiply)


def _guard_sustained_noise_suppress(out: ScoreVector, f: DSPFeatures, c: SustainedNoiseSuppressConfig) -> None:
    # 매우 지속적 + 노이즈성이면 core/accent 억제
    if (f.decay_time >= c.decay_long_threshold) and (f.spectral_flatness >= c.flatness_threshold):
        _mul(out, Role.CORE, c.core_multiply)
        _mul(out, Role.ACCENT, c.accent_multiply)


def _guard_motion_min_condition(out: ScoreVector, f: DSPFeatures, c: MotionMinConditionConfig) -> None:
    # motion은 고역 비율이 충분하고 너무 길지 않아야 함
    if (f.high_ratio < c.high_ratio_threshold) or (f.decay_time > c.decay_max_threshold):
        _mul(out, Role.MOTION, c.multiply)


def _guard_fill_conservative(out: ScoreVector, margin: float, c: FillConservativeConfig) -> None:
    # fill은 확신할 때만
    fill_p = float(out.values.get(Role.FILL, 0.0))
    if (fill_p < c.min_prob) or (margin < c.min_margin):
        _mul(out, Role.FILL, c.multiply)


def _guard_low_conf_texture_extra(out: ScoreVector, margin: float, c: LowConfTextureExtraSuppressConfig) -> None:
    if not c.enabled:
        return
    if margin >= c.margin_threshold:
        return

    # 현재 1등이 TEXTURE이고 2등이 타격계열이면 TEXTURE 추가 억제
    sorted_roles = out.sorted()
    if len(sorted_roles) < 2:
        return

    top_role = sorted_roles[0][0]
    second_role = sorted_roles[1][0]

    if top_role != Role.TEXTURE:
        return

    percussive = set(c.percussive_roles)
    if second_role.value in percussive:
        _mul(out, Role.TEXTURE, c.multiply)