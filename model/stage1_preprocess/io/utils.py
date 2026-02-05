"""Utility functions for DrumGen-X."""

import os
import logging
from pathlib import Path
from typing import Tuple

import librosa
import numpy as np
import soundfile as sf


logger = logging.getLogger("preprocess")


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="[%(name)s] %(message)s",
    )


def set_torch_home() -> None:
    """Set TORCH_HOME to avoid D:\\ path issues on Windows with demucs."""
    cache_dir = str(Path.home() / ".cache" / "torch")
    os.environ["TORCH_HOME"] = cache_dir
    os.environ["TORCH_HUB"] = cache_dir
    logger.debug(f"TORCH_HOME={cache_dir}")


def load_audio(path: Path, sr: int = 44100) -> Tuple[np.ndarray, int]:
    y, loaded_sr = librosa.load(path, sr=sr, mono=True)
    return y, loaded_sr


def save_audio(path: Path, y: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), y, sr)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
