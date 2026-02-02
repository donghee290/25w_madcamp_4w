from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from .types import Role, SampleResult, ScoreBundle
from .dsp.audio_io import AudioLoadConfig, load_audio
from .dsp.features import DSPConfig, extract_features
from .dsp.rule_scoring import RuleScoringConfig, compute_rule_scores
from .clap.backend import ClapBackend, ClapBackendConfig
from .clap.scoring import ClapScorer, ClapScoringConfig
from .fusion.fuse import FusionConfig, fuse_rule_and_clap, build_score_bundle


@dataclass
class RoleAssignerConfig:
    # audio io
    audio: AudioLoadConfig

    # dsp
    dsp: DSPConfig
    rule_scoring: RuleScoringConfig

    # clap
    clap_backend: ClapBackendConfig
    clap_scoring: ClapScoringConfig

    # fusion
    fusion: FusionConfig


class RoleAssigner:
    """
    입력 오디오(원샷) -> 역할 판단 결과(SampleResult)
    """

    def __init__(self, cfg: RoleAssignerConfig):
        self.cfg = cfg

        # CLAP은 무거우니까 한번만 로드
        self.clap_backend = ClapBackend(cfg.clap_backend)
        self.clap_scorer = ClapScorer(self.clap_backend, cfg.clap_scoring)

    def assign_file(self, filepath: str | Path, sample_id: Optional[str] = None) -> SampleResult:
        path = Path(filepath)
        sid = sample_id or path.stem

        y, sr = load_audio(path, self.cfg.audio)

        return self.assign_audio(y=y, sr=sr, sample_id=sid, filepath=str(path))

    def assign_audio(
        self,
        y: np.ndarray,
        sr: int,
        sample_id: str = "sample",
        filepath: str = "",
    ) -> SampleResult:
        # 1) DSP features
        feats = extract_features(y, sr, self.cfg.dsp)

        # 2) rule score -> p_rule
        rule_raw, p_rule = compute_rule_scores(feats, self.cfg.rule_scoring)

        # 3) CLAP similarity -> p_clap
        sim_role, p_clap = self.clap_scorer.score(y, sr)

        # 4) fuse -> p_final + confidence
        p_final, margin = fuse_rule_and_clap(
            p_rule=p_rule,
            p_clap=p_clap,
            features=feats,
            cfg=self.cfg.fusion,
        )

        role = p_final.argmax()

        bundle: ScoreBundle = build_score_bundle(p_rule=p_rule, p_clap=p_clap, p_final=p_final)

        return SampleResult(
            sample_id=sample_id,
            filepath=filepath,
            role=role,
            scores=bundle,
            features=feats,
            clap_similarities={r: float(sim_role[r]) for r in sim_role},
            rule_raw_scores={r: float(rule_raw[r]) for r in rule_raw},
        )