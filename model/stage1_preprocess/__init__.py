"""stage1_preprocess — DrumGen-X audio preprocessing pipeline."""

# I/O utilities
from .io.utils import load_audio, save_audio, ensure_dir, setup_logging

# Dataset scanning
from .io.ingest import scan_dataset, random_sample, generate_report

# Source separation
from .separation.separator import extract_drum_stem

# Analysis
from .analysis.features import extract_dsp_features
from .analysis.detector import detect_onsets

# Slicing
from .slicing.slicer import slice_hits, normalize_hit, save_samples, extract_samples

# Deduplication
from .cleaning.dedup import deduplicate_hits

# Configuration
from .config import PipelineConfig

__all__ = [
    # I/O
    "load_audio", "save_audio", "ensure_dir", "setup_logging",
    "scan_dataset", "random_sample", "generate_report",
    # Separation
    "extract_drum_stem",
    # Analysis
    "extract_dsp_features", "detect_onsets",
    # Slicing
    "slice_hits", "normalize_hit", "save_samples", "extract_samples",
    # Deduplication
    "deduplicate_hits",
    # Config
    "PipelineConfig",
]
