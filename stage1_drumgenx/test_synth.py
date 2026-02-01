"""Quick synthesis test for DrumGen-X kits."""

from pathlib import Path

from .config import SequencerConfig
from .sequencer import (
    DrumPattern,
    PatternTemplates,
    generate_variation,
    load_kit,
    render_and_save,
)
from .utils import logger, ensure_dir


def quick_test(
    kit_dir: Path,
    output_dir: Path = None,
    sr: int = 44100,
    bpm: float = 120.0,
    bars: int = 4,
    pattern_name: str = "rock",
) -> Path:
    """Generate a test loop from an organized kit directory.

    Returns path to the rendered WAV file.
    """
    if output_dir is None:
        output_dir = kit_dir / "test_loops"
    ensure_dir(output_dir)

    kit = load_kit(kit_dir, sr=sr)
    if not kit:
        raise ValueError(f"No samples found in kit directory: {kit_dir}")

    # Select pattern template
    templates = {
        "rock": PatternTemplates.rock_basic,
        "hiphop": PatternTemplates.hiphop,
        "jazz": PatternTemplates.jazz,
    }

    if pattern_name not in templates:
        raise ValueError(f"Unknown pattern: {pattern_name}. Available: {list(templates.keys())}")

    pattern = templates[pattern_name](bars=bars)
    output_path = output_dir / f"test_{pattern_name}_{int(bpm)}bpm.wav"
    render_and_save(pattern, kit, output_path, sr=sr, bpm=bpm)

    # Also generate a variation
    var_pattern = generate_variation(pattern, variation_pct=0.15)
    var_path = output_dir / f"test_{pattern_name}_var_{int(bpm)}bpm.wav"
    render_and_save(var_pattern, kit, var_path, sr=sr, bpm=bpm)

    logger.info(f"Test loops saved to {output_dir}")
    return output_path


def test_all_patterns(
    kit_dir: Path,
    output_dir: Path = None,
    sr: int = 44100,
    bpm: float = 120.0,
    bars: int = 4,
) -> Path:
    """Generate test loops for all pattern templates."""
    if output_dir is None:
        output_dir = kit_dir / "test_loops"
    ensure_dir(output_dir)

    for pattern_name in ["rock", "hiphop", "jazz"]:
        quick_test(kit_dir, output_dir, sr, bpm, bars, pattern_name)

    return output_dir
