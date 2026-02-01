from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

import numpy as np

from ..types import DSPFeatures, Role, ScoreVector


@dataclass
class TexturePenaltyConfig:
    enabled: bool = True
    transient_S_threshold: float = 0.55
    decay_short_threshold: float = 0.35
    penalty: float = 0.18

    use_flatness_gate: bool = True
    flatness_threshold: float = 0.18
    flatness_penalty: float = 0.10


@dataclass
class RuleWeights:
    # 각 role별 feature weight dict
    core: Dict[str, float]
    accent: Dict[str, float]
    motion: Dict[str, float]
    fill: Dict[str, float]
    texture: Dict[str, float]


@dataclass
class RuleScoringConfig:
    weights: RuleWeights
    tau_rule: float = 0.95
    texture_penalty: TexturePenaltyConfig = field(default_factory=TexturePenaltyConfig)


def compute_rule_scores(
    f: DSPFeatures,
    cfg: RuleScoringConfig,
) -> Tuple[Dict[Role, float], ScoreVector]:
    """
    DSPFeatures -> rule raw scores + p_rule(softmax)
    returns:
      - raw_scores: role -> float (soft score)
      - p_rule: ScoreVector(role->prob)
    """
    raw = _raw_rule_scores(f, cfg.weights)

    if cfg.texture_penalty and cfg.texture_penalty.enabled:
        raw = _apply_texture_penalty(raw, f, cfg.texture_penalty)

    p_rule = _softmax_dict(raw, tau=max(cfg.tau_rule, 1e-6))
    return raw, p_rule


# =========================
# Internal: raw scores
# =========================

def _raw_rule_scores(f: DSPFeatures, w: RuleWeights) -> Dict[Role, float]:
    """
    DSP Rule Scoring (Hardcoded per user request)

    1. CORE (Kick-like)
       Score = 0.40L + 0.25(1-A) + 0.25(1-D) + 0.10(1-S)

    2. ACCENT (Snare-like)
       Score = 0.35E + 0.35S + 0.20M + 0.10(1-D)

    3. MOTION (Hi-hat/Shaker-like)
       Score = 0.40H + 0.20(1-E) + 0.25(1-D) + 0.15S

    4. FILL (Tom/FX-like)
       Score = 0.30E + 0.35D + 0.25S + 0.10M
       * Note: Uses D (not 1-D)

    5. TEXTURE (Background/Cymbal-like)
       Score = 0.45D + 0.25(1-S) + 0.20(L+M) + 0.10(1-E)
       * Note: Uses D, 1-S, L+M, 1-E
    """
    E = f.energy
    S = f.sharpness
    L, M, H = f.low_ratio, f.mid_ratio, f.high_ratio
    # A_fast = 1 - A (already clip01)
    # D_short = 1 - D (already clip01)
    A_fast = f.A_fast
    D_short = f.D_short
    D = f.decay_time

    # CORE (Kick-like)
    # Reward: Low, Fast Attack, Short Decay
    # Penalty: High Freq (Kick shouldn't be hissy), Flatness (Kick shouldn't be pure noise)
    score_core = (
        0.40 * L
        + 0.25 * A_fast
        + 0.25 * D_short
        + 0.10 * (1.0 - S)
        - 0.50 * H          # Penalty: High freq content
        - 0.30 * f.spectral_flatness # Penalty: Noise
    )

    # ACCENT (Snare-like)
    # Reward: Mid, Sharpness, Energy
    # Penalty: Low Ratio (Snare shouldn't be too boomy)
    score_accent = (
        0.35 * E
        + 0.35 * S
        + 0.20 * M
        + 0.10 * D_short
        - 0.30 * L          # Penalty: Too much bass
    )

    # MOTION (Hi-hat/Shaker-like)
    # Reward: High, low energy (relative), short decay
    # Penalty: Low Ratio (Hats shouldn't have bass)
    score_motion = (
        0.40 * H
        + 0.20 * (1.0 - E)
        + 0.25 * D_short
        + 0.15 * S
        - 0.50 * L          # Penalty: Bass content
    )

    # FILL (Tom/FX-like)
    # Reward: Energy, Decay (longer than others), Sharpness
    # Penalty: Flatness (Pure noise is usually Texture or Motion)
    score_fill = (
        0.30 * E
        + 0.35 * D
        + 0.25 * S
        + 0.10 * M
        - 0.20 * f.spectral_flatness # Penalty: Noise
    )

    # TEXTURE (Background/Cymbal-like)
    # Reward: Decay (Long), Noise-like (1-S or Flatness), distributed freq
    # Penalty: Sharpness/Transient (Texture shouldn't be punchy)
    score_texture = (
        0.45 * D
        + 0.25 * (1.0 - S)
        + 0.20 * (L + M)
        + 0.10 * (1.0 - E)
        - 0.30 * S          # Penalty: Sharpness
    )

    return {
        Role.CORE: float(score_core),
        Role.ACCENT: float(score_accent),
        Role.MOTION: float(score_motion),
        Role.FILL: float(score_fill),
        Role.TEXTURE: float(score_texture),
    }


def _apply_texture_penalty(
    raw: Dict[Role, float],
    f: DSPFeatures,
    p: TexturePenaltyConfig,
) -> Dict[Role, float]:
    """
    텍스처 쏠림 방지:
    - transient가 강하고 decay가 짧으면 texture 점수 감점
    - noise-like(flatness)가 낮으면 texture 점수 감점(선택)
    """
    raw2 = dict(raw)

    # 1) 타격성인데 texture로 튀는 것 방지
    if (f.sharpness >= p.transient_S_threshold) and (f.decay_time <= p.decay_short_threshold):
        raw2[Role.TEXTURE] = float(raw2[Role.TEXTURE] - p.penalty)

    # 2) flatness 낮은데 texture가 이기는 것 방지(선택)
    if p.use_flatness_gate and (f.spectral_flatness <= p.flatness_threshold):
        raw2[Role.TEXTURE] = float(raw2[Role.TEXTURE] - p.flatness_penalty)

    return raw2


# =========================
# Softmax helpers
# =========================

def _softmax_dict(scores: Dict[Role, float], tau: float = 1.0) -> ScoreVector:
    """
    scores를 softmax로 확률로 변환.
    """
    roles = list(scores.keys())
    x = np.array([scores[r] for r in roles], dtype=np.float32)

    # temperature
    x = x / float(tau)

    # 안정화: max shift
    x = x - np.max(x)
    ex = np.exp(x)
    denom = float(np.sum(ex)) + 1e-12
    probs = ex / denom

    sv = ScoreVector(values={roles[i]: float(probs[i]) for i in range(len(roles))})
    return sv


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + float(np.exp(-x)))