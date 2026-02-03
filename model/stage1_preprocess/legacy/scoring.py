"""Rule-based Score Calculation for Drum Roles."""

import numpy as np
from typing import Dict, List, Tuple, Optional
from enum import Enum

class DrumRole(str, Enum):
    CORE = "core"       # Kick-like
    ACCENT = "accent"   # Snare-like
    MOTION = "motion"   # Hihat-like
    FILL = "fill"       # Tom-like / Long impact
    TEXTURE = "texture" # Background / FX

def calculate_role_scores(features: Dict[str, float]) -> Dict[DrumRole, float]:
    """Calculate scores for each role based on DSP features."""
    
    E = features["energy"]
    S = features["sharpness"]
    L = features["band_low"]
    M = features["band_mid"]
    H = features["band_high"]
    A = features["attack_time"] # seconds
    D = features["decay_time"]  # seconds

    # Normalize A and D roughly to 0-1 for formulas
    # Attack: typically < 0.05s. If > 0.1s, it's slow.
    A_norm = np.clip(A / 0.1, 0, 1)
    
    # Decay: short < 0.2s, long > 0.5s
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
        DrumRole.CORE: score_core,
        DrumRole.ACCENT: score_accent,
        DrumRole.MOTION: score_motion,
        DrumRole.FILL: score_fill,
        DrumRole.TEXTURE: score_texture
    }

def get_best_role(scores: Dict[DrumRole, float]) -> Tuple[DrumRole, float]:
    """Return the role with the highest score."""
    best_role = max(scores, key=scores.get)
    return best_role, scores[best_role]


def normalize_scores_softmax(scores: Dict[DrumRole, float], tau: float = 1.0) -> Dict[DrumRole, float]:
    """Normalize role scores to probabilities using softmax with temperature."""
    roles = list(scores.keys())
    vals = np.array([scores[r] for r in roles])
    # Apply temperature scaling
    scaled = vals / max(tau, 1e-8)
    # Softmax
    exp_vals = np.exp(scaled - np.max(scaled))  # numerical stability
    probs = exp_vals / np.sum(exp_vals)
    return {r: float(p) for r, p in zip(roles, probs)}


def fuse_scores(
    rule_scores: Dict[DrumRole, float],
    classifier_probs: Optional[Dict[DrumRole, float]],
    alpha: float = 1.0,
    tau: float = 1.0,
) -> Dict[DrumRole, float]:
    """Fuse rule-based scores with classifier probabilities.

    final = alpha * softmax(rule/tau) + (1-alpha) * classifier_probs
    If classifier_probs is None, uses rule scores only (alpha=1.0 effectively).
    """
    rule_probs = normalize_scores_softmax(rule_scores, tau)

    if classifier_probs is None or alpha >= 1.0:
        return rule_probs

    final = {}
    for role in DrumRole:
        r = rule_probs.get(role, 0.0)
        c = classifier_probs.get(role, 0.0)
        final[role] = alpha * r + (1.0 - alpha) * c

    # Re-normalize to sum to 1
    total = sum(final.values())
    if total > 0:
        final = {r: v / total for r, v in final.items()}

    return final


def calculate_confidence(final_scores: Dict[DrumRole, float]) -> float:
    """Calculate classification confidence as margin between top two scores."""
    sorted_vals = sorted(final_scores.values(), reverse=True)
    if len(sorted_vals) < 2:
        return sorted_vals[0] if sorted_vals else 0.0
    return sorted_vals[0] - sorted_vals[1]


def get_best_role_with_confidence(
    features: Dict[str, float],
    classifier_probs: Optional[Dict[DrumRole, float]] = None,
    alpha: float = 1.0,
    tau: float = 1.0,
) -> Tuple[DrumRole, float, float, Dict[DrumRole, float]]:
    """Full pipeline: features -> scores -> fusion -> role + confidence.

    Returns (role, best_score, confidence, final_scores).
    """
    rule_scores = calculate_role_scores(features)
    final = fuse_scores(rule_scores, classifier_probs, alpha, tau)
    role = max(final, key=final.get)
    conf = calculate_confidence(final)
    return role, final[role], conf, final
