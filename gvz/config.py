from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Pass1Config:
    input_dir: Path
    report_dir: Path
    sr: int
    n_mfcc: int
    low_threshold: float
    high_threshold: float
    num_workers: int
    dbscan_eps: float
    dbscan_min_samples: int
    use_harmonic: bool
    auto_threshold: bool
    auto_low_quantile: float
    auto_high_quantile: float
    include_name: Optional[str]


@dataclass
class Pass2Config:
    manifest_path: Path
    output_dir: Path
    sr: int
    gain_db: float
    highcut_hz: Optional[float]
    highcut_order: int
    eq_5k_db: float
    eq_10k_db: float
    eq_q: float
    notch_hz: Optional[float]
    notch_q: float
    gate_enabled: bool
    gate_threshold_db: float
    gate_attack_ms: float
    gate_release_ms: float
    denoise_enabled: bool
    denoise_strength: float
    denoise_quantile: float
    denoise_profile_sec: Optional[float]
    denoise_time_smooth: int
    deesser_enabled: bool
    deesser_low_hz: float
    deesser_high_hz: float
    deesser_threshold_db: float
    deesser_ratio: float
    deesser_attack_ms: float
    deesser_release_ms: float
    noise_split_enabled: bool
    noise_threshold_db: float
    noise_window_sec: float
    clean_gain_db: float
    clean_denoise_strength: float
    clean_deesser_threshold_db: float
    clean_deesser_ratio: float
    noisy_gain_db: float
    noisy_denoise_strength: float
    noisy_deesser_threshold_db: float
    noisy_deesser_ratio: float

