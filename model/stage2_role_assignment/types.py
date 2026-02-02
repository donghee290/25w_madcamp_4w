from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# =========================
# Role enum
# =========================

class Role(str, Enum):
    CORE = "CORE"
    ACCENT = "ACCENT"
    MOTION = "MOTION"
    FILL = "FILL"
    TEXTURE = "TEXTURE"

    @classmethod
    def list(cls) -> List["Role"]:
        return [cls.CORE, cls.ACCENT, cls.MOTION, cls.FILL, cls.TEXTURE]


# =========================
# DSP feature container
# =========================

@dataclass
class DSPFeatures:
    # energy / loudness
    energy: float                     # E (0~1)
    rms: float                        # 보조 지표 (0~1)

    # transient / time
    sharpness: float                  # S (spectral flux 기반, 0~1)
    attack_time: float                # seconds
    decay_time: float                 # seconds

    # band energy ratio (합=1)
    low_ratio: float                  # L
    mid_ratio: float                  # M
    high_ratio: float                 # H

    # noise-related
    spectral_flatness: float          # 0~1 (noise-like)
    zero_crossing_rate: float         # 0~1 (고역/노이즈 힌트)

    # convenience helpers
    @property
    def A_fast(self) -> float:
        # attack 빠를수록 큼
        return 1.0 - self._clip01(self.attack_time)

    @property
    def D_short(self) -> float:
        # decay 짧을수록 큼
        return 1.0 - self._clip01(self.decay_time)

    @property
    def one_minus_energy(self) -> float:
        return 1.0 - self.energy

    @property
    def one_minus_sharpness(self) -> float:
        return 1.0 - self.sharpness

    @staticmethod
    def _clip01(x: float) -> float:
        if x < 0.0:
            return 0.0
        if x > 1.0:
            return 1.0
        return x


# =========================
# Score containers
# =========================

@dataclass
class ScoreVector:
    """
    role -> score/probability mapping
    """
    values: Dict[Role, float] = field(default_factory=dict)

    def argmax(self) -> Role:
        return max(self.values.items(), key=lambda kv: kv[1])[0]

    def sorted(self) -> List[tuple[Role, float]]:
        return sorted(self.values.items(), key=lambda kv: kv[1], reverse=True)

    def max_value(self) -> float:
        return max(self.values.values())

    def second_max_value(self) -> float:
        if len(self.values) < 2:
            return 0.0
        sorted_vals = self.sorted()
        return sorted_vals[1][1]

    def margin(self) -> float:
        return self.max_value() - self.second_max_value()

    def normalize(self) -> "ScoreVector":
        s = sum(self.values.values())
        if s <= 0:
            return self
        for k in self.values:
            self.values[k] /= s
        return self

    def clone(self) -> "ScoreVector":
        return ScoreVector(values=dict(self.values))


@dataclass
class ScoreBundle:
    """
    All scores for a sample
    """
    rule: ScoreVector               # p_rule
    clap: ScoreVector               # p_clap
    final: ScoreVector              # p_final
    confidence: float               # margin


# =========================
# Per-sample result
# =========================

@dataclass
class SampleResult:
    sample_id: str                  # 파일명 or UUID
    filepath: str

    role: Role                      # 최종 role
    scores: ScoreBundle
    features: DSPFeatures

    # CLAP raw similarity (debug)
    clap_similarities: Optional[Dict[Role, float]] = None

    # rule raw score (debug)
    rule_raw_scores: Optional[Dict[Role, float]] = None


# =========================
# Pool container
# =========================

@dataclass
class RolePools:
    core: List[SampleResult] = field(default_factory=list)
    accent: List[SampleResult] = field(default_factory=list)
    motion: List[SampleResult] = field(default_factory=list)
    fill: List[SampleResult] = field(default_factory=list)
    texture: List[SampleResult] = field(default_factory=list)

    def get(self, role: Role) -> List[SampleResult]:
        if role == Role.CORE:
            return self.core
        if role == Role.ACCENT:
            return self.accent
        if role == Role.MOTION:
            return self.motion
        if role == Role.FILL:
            return self.fill
        if role == Role.TEXTURE:
            return self.texture
        raise ValueError(f"Unknown role: {role}")

    def as_dict(self) -> Dict[str, List[SampleResult]]:
        return {
            "CORE": self.core,
            "ACCENT": self.accent,
            "MOTION": self.motion,
            "FILL": self.fill,
            "TEXTURE": self.texture,
        }