"""Dataset scanning and random sampling for DrumGen-X."""

import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import librosa

from .utils import logger


AUDIO_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".aif", ".aiff"}


def scan_dataset(root_dir: Path) -> List[Path]:
    """Recursively find all audio files in the dataset directory."""
    root = Path(root_dir)
    if not root.exists():
        raise FileNotFoundError(f"Dataset root not found: {root}")

    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )
    logger.info(f"Found {len(files)} audio files in {root}")
    return files


def random_sample(paths: List[Path], n: int, seed: Optional[int] = None) -> List[Path]:
    """Pick n random files from the list."""
    if seed is not None:
        random.seed(seed)
    n = min(n, len(paths))
    return random.sample(paths, n)


@dataclass
class DatasetReport:
    root: str
    total_files: int
    directories: dict  # dirname -> count
    sample_durations: dict  # path -> duration_s (for sampled files)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def generate_report(
    root_dir: Path,
    sample_n: int = 5,
    sr: int = 44100,
) -> DatasetReport:
    """Scan dataset and generate a summary report."""
    files = scan_dataset(root_dir)

    # Count by directory
    dir_counts: dict = {}
    for f in files:
        dirname = f.parent.name
        dir_counts[dirname] = dir_counts.get(dirname, 0) + 1

    # Sample a few files for duration check
    sampled = random_sample(files, sample_n)
    durations = {}
    for p in sampled:
        try:
            dur = librosa.get_duration(path=str(p))
            durations[str(p.name)] = round(dur, 2)
        except Exception as e:
            durations[str(p.name)] = f"error: {e}"

    return DatasetReport(
        root=str(root_dir),
        total_files=len(files),
        directories=dir_counts,
        sample_durations=durations,
    )
