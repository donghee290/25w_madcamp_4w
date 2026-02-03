"""Rule-based Score Calculation for Drum Roles."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Tuple

import numpy as np


class DrumRole(str, Enum):
    CORE = "core"       # Kick-like
    ACCENT = "accent"   # Snare-like
    MOTION = "motion"   # Hihat-like
    FILL = "fill"       # Tom-like / Long impact
    TEXTURE = "texture" # Background / FX


def calculate_role_scores(features: Dict[str, float]) -> Dict[DrumRole, float]:
    """Calculate scores for each role based on DSP features."""
    E = features.get("energy", 0.0)
    S = features.get("sharpness", 0.0)
    L = features.get("band_low", 0.0)
    M = features.get("band_mid", 0.0)
    H = features.get("band_high", 0.0)
    A = features.get("attack_time", 0.0)  # seconds
    D = features.get("decay_time", 0.0)   # seconds

    # Normalize A and D roughly to 0-1 for formulas
    A_norm = np.clip(A / 0.1, 0, 1)
    D_norm = np.clip(D / 1.0, 0, 1)

    # Auxiliary scalars
    A_fast = 1.0 - A_norm
    D_short = 1.0 - D_norm

    # 1. CORE: Low, Fast Attack, Short-ish decay, Not too sharp
    score_core = (
        0.40 * L +
        0.25 * A_fast +
        0.25 * D_short +
        0.10 * (1.0 - S)
    )

    # 2. ACCENT: High Energy, Sharp, Mid-heavy, Not too long
    score_accent = (
        0.35 * E +
        0.35 * S +
        0.20 * M +
        0.10 * D_short
    )

    # 3. MOTION: High freq, Low Energy (light), Short, Sharp
    score_motion = (
        0.40 * H +
        0.20 * (1.0 - E) +
        0.25 * D_short +
        0.15 * S
    )

    # 4. FILL: High Energy, Long Decay, Sharp, Mid freq
    score_fill = (
        0.30 * E +
        0.35 * D_norm +
        0.25 * S +
        0.10 * M
    )

    # 5. TEXTURE: Long Decay, Smooth (Not sharp), Low/Mid context, Low Energy
    score_texture = (
        0.45 * D_norm +
        0.25 * (1.0 - S) +
        0.20 * (L + M) +
        0.10 * (1.0 - E)
    )

    return {
        DrumRole.CORE: float(score_core),
        DrumRole.ACCENT: float(score_accent),
        DrumRole.MOTION: float(score_motion),
        DrumRole.FILL: float(score_fill),
        DrumRole.TEXTURE: float(score_texture),
    }


def get_best_role(scores: Dict[DrumRole, float]) -> Tuple[DrumRole, float]:
    """Return the role with the highest score."""
    best_role = max(scores, key=scores.get)
    return best_role, float(scores[best_role])


def normalize_scores_softmax(scores: Dict[DrumRole, float], tau: float = 1.0) -> Dict[DrumRole, float]:
    """Normalize role scores to probabilities using softmax with temperature."""
    roles = list(scores.keys())
    vals = np.array([scores[r] for r in roles], dtype=np.float32)
    scaled = vals / max(tau, 1e-8)
    exp_vals = np.exp(scaled - np.max(scaled))
    probs = exp_vals / np.sum(exp_vals)
    return {r: float(p) for r, p in zip(roles, probs)}


def fuse_scores(
    rule_scores: Dict[DrumRole, float],
    classifier_probs: Optional[Dict[DrumRole, float]],
    alpha: float = 1.0,
    tau: float = 1.0,
) -> Dict[DrumRole, float]:
    """Fuse rule-based scores with classifier probabilities."""
    rule_probs = normalize_scores_softmax(rule_scores, tau)

    if classifier_probs is None or alpha >= 1.0:
        return rule_probs

    final = {}
    for role in DrumRole:
        r = rule_probs.get(role, 0.0)
        c = classifier_probs.get(role, 0.0)
        final[role] = alpha * r + (1.0 - alpha) * c

    total = sum(final.values())
    if total > 0:
        final = {r: v / total for r, v in final.items()}

    return final


def calculate_confidence(final_scores: Dict[DrumRole, float]) -> float:
    """Calculate classification confidence as margin between top two scores."""
    sorted_vals = sorted(final_scores.values(), reverse=True)
    if len(sorted_vals) < 2:
        return sorted_vals[0] if sorted_vals else 0.0
    return float(sorted_vals[0] - sorted_vals[1])


def get_best_role_with_confidence(
    features: Dict[str, float],
    classifier_probs: Optional[Dict[DrumRole, float]] = None,
    alpha: float = 1.0,
    tau: float = 1.0,
) -> Tuple[DrumRole, float, float, Dict[DrumRole, float]]:
    """Full pipeline: features -> scores -> fusion -> role + confidence."""
    rule_scores = calculate_role_scores(features)
    final = fuse_scores(rule_scores, classifier_probs, alpha, tau)
    role = max(final, key=final.get)
    conf = calculate_confidence(final)
    return role, float(final[role]), float(conf), final
