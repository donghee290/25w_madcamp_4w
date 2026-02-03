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
from .slicing.slicer import slice_hits, normalize_hit, classify_and_organize, build_kit_from_audio

# Deduplication
from .cleaning.dedup import deduplicate_hits

# Role scoring (root-level modules)
from .scoring import DrumRole, calculate_role_scores, get_best_role, fuse_scores, normalize_scores_softmax, calculate_confidence, get_best_role_with_confidence

# Pool balancing
from .pool_balancer import balance_pools

# Event grid & sequencing
from .events import DrumEvent, EventGrid, generate_skeleton, display_grid

# Sequencer (rendering)
from .sequencer import load_kit, render_event_grid, render_and_save

# Configuration
from .config import PipelineConfig, SequencerConfig, DrumClass

__all__ = [
    # I/O
    "load_audio", "save_audio", "ensure_dir", "setup_logging",
    "scan_dataset", "random_sample", "generate_report",
    # Separation
    "extract_drum_stem",
    # Analysis
    "extract_dsp_features", "detect_onsets",
    # Slicing
    "slice_hits", "normalize_hit", "classify_and_organize", "build_kit_from_audio",
    # Deduplication
    "deduplicate_hits",
    # Scoring
    "DrumRole", "calculate_role_scores", "get_best_role", "fuse_scores",
    "normalize_scores_softmax", "calculate_confidence", "get_best_role_with_confidence",
    # Pool
    "balance_pools",
    # Events
    "DrumEvent", "EventGrid", "generate_skeleton", "display_grid",
    # Sequencer
    "load_kit", "render_event_grid", "render_and_save",
    # Config
    "PipelineConfig", "SequencerConfig", "DrumClass",
]
