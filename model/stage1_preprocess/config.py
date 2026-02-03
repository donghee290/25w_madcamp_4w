"""Configuration dataclasses and enums for DrumGen-X."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class DrumClass(str, Enum):
    KICK = "kick"
    SNARE = "snare"
    HIHAT = "hihat"
    CRASH = "crash"
    RIDE = "ride"
    LTOM = "ltom"
    RTOM = "rtom"
    ROWTOM = "rowtom"
    UNKNOWN = "unknown"


@dataclass
class ClassifierThresholds:
    # Kick: low centroid, wide bandwidth, low ZCR
    kick_centroid_max: float = 300.0
    kick_zcr_max: float = 0.05

    # Snare: mid centroid, very wide bandwidth, high ZCR
    snare_centroid_min: float = 1000.0
    snare_centroid_max: float = 4000.0
    snare_zcr_min: float = 0.15

    # Hi-hat: very high centroid, very high ZCR
    hihat_centroid_min: float = 5000.0
    hihat_zcr_min: float = 0.3

    # Crash: high centroid, wide bandwidth, long duration
    crash_centroid_min: float = 3000.0
    crash_duration_min: float = 0.5

    # Ride: high centroid, medium bandwidth, medium ZCR
    ride_centroid_min: float = 3000.0
    ride_zcr_max: float = 0.3
    ride_duration_max: float = 0.5

    # Tom pitch ranges (Hz) via pYIN
    ltom_pitch_min: float = 80.0
    ltom_pitch_max: float = 150.0
    rtom_pitch_min: float = 150.0
    rtom_pitch_max: float = 300.0
    rowtom_pitch_min: float = 300.0
    rowtom_pitch_max: float = 500.0

    # Tom general: mid-low centroid, low ZCR
    tom_centroid_min: float = 100.0
    tom_centroid_max: float = 800.0
    tom_zcr_max: float = 0.15


@dataclass
class PipelineConfig:
    sr: int = 44100
    demucs_model: str = "htdemucs"
    demucs_device: str = "cuda"
    chunk_duration_s: float = 60.0

    dataset_root: Path = Path(
        r"C:\Project\kaist\4_week\165.가상공간 환경음 매칭 데이터"
        r"\01-1.정식개방데이터\Training\01.원천데이터"
    )
    output_root: Path = Path(r"C:\Project\kaist\4_week\drumgenx_output")

    # Onset detection
    # Increased to 100ms to avoid over-segmentation of single hits (e.g. reverb tails, flam)
    # This ensures slices are longer and more "meaningful".
    onset_merge_ms: float = 100.0
    onset_backtrack: bool = True

    # Slicer
    max_hit_duration_s: float = 2.0
    fade_out_ms: float = 50.0
    trim_silence_db: float = 70.0
    
    # One-shot handling
    one_shot_threshold_s: float = 10.0

    # Classifier (deprecated - kept for backward compatibility)
    thresholds: ClassifierThresholds = field(default_factory=ClassifierThresholds)

    # Role scoring
    alpha: float = 1.0          # rule vs classifier weight (1.0 = rule only)
    tau: float = 1.0            # softmax temperature for rule scores

    # Pool constraints
    pool_min_core: int = 1
    pool_min_accent: int = 1
    pool_min_motion: int = 1

    # Sequencer
    max_poly: int = 3           # max simultaneous sounds per step

    # Deduplication
    dedup_enabled: bool = True
    dedup_enabled: bool = True
    dedup_threshold: float = 0.5  # cosine distance threshold
    min_hit_duration_s: float = 0.1  # discard hits shorter than 100ms

    # ML features (disabled by default)
    yamnet_enabled: bool = False
    groovae_enabled: bool = False

    # Number of files to process in pipeline mode
    n_files: int = 5

    # Best samples per class for master kit
    best_per_class: int = 10
    
    # Max samples to extract per file (post-dedup)
    max_extracted_samples: int = 5


@dataclass
class SequencerConfig:
    bpm: float = 120.0
    bars: int = 4
    grid_resolution: int = 16  # 16th notes per bar
    velocity_humanize: float = 0.1  # +/- dB variation
