"""Single-script Audio Preprocessor.

Runs the extraction pipeline on a single audio file:
1. Demucs (Separation)
2. Onset Detection
3. Slicing
4. DSP Classification
5. Saving to Kit folder

Usage:
    python run_preprocess.py <path_to_audio_file>
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("drumgenx")

try:
    from drumgenx.separator import extract_drum_stem
    from drumgenx.detector import detect_onsets
    from drumgenx.slicer import build_kit_from_audio
    from drumgenx.utils import load_audio, ensure_dir
except ImportError:
    print("Error: drumgenx package not found. Run this from the parent directory.")
    sys.exit(1)

def run_preprocess(audio_path_str: str, output_root: str = "preprocess_output"):
    # 0. Check input
    audio_path = Path(audio_path_str)
    if not audio_path.exists():
        logger.error(f"File not found: {audio_path}")
        return

    logger.info(f"=== Starting Preprocessing for {audio_path.name} ===")
    
    # Prepare output dirs
    out_dir = ensure_dir(Path(output_root))
    file_dir = ensure_dir(out_dir / audio_path.stem)
    
    # 1. Separation (Demucs)
    logger.info("[1/4] Separating Drums (Demucs)...")
    # Using default config: htdemucs, cuda/cpu automatically
    drums_path = extract_drum_stem(
        audio_path, 
        file_dir / "demucs",
        model="htdemucs",
        device="cuda" if sys.platform != "darwin" else "cpu" # naive check
    )
    
    # 2. Load Stem
    logger.info(f"[2/4] Loading Separated Audio: {drums_path}")
    y, sr = load_audio(drums_path, sr=44100)
    
    # 3. Detection
    logger.info("[3/4] Detecting Onsets...")
    onsets = detect_onsets(y, sr, merge_ms=30, backtrack=True)
    logger.info(f"    -> Found {len(onsets)} onsets")
    
    if not onsets:
        logger.warning("No onsets found. Exiting.")
        return

    # 4. Slicing & Classification
    logger.info("[4/4] Slicing and Classifying...")
    kit_dir = file_dir / "kit"
    manifest_path, organized = build_kit_from_audio(
        y, sr, onsets, kit_dir,
        max_duration_s=1.5,
        fade_out_ms=10.0
    )
    
    # Summary
    logger.info(f"=== Done! Output saved to: {kit_dir} ===")
    print(f"\nSuccess! Kit created at:\n{kit_dir.absolute()}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_preprocess.py <audio_file>")
        sys.exit(1)
        
    run_preprocess(sys.argv[1])
