from __future__ import annotations

from pathlib import Path


def preprocess_long_audio(input_path: Path, output_dir: Path) -> Path:
    """
    Placeholder for Stage1 preprocessing (long audio -> oneshots).
    If you want to support this mode, call pipeline/run_preprocess.py or
    integrate stage1_drumgenx utilities directly.
    """
    raise NotImplementedError("Stage1 preprocess is not wired in API yet.")
