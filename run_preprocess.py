"""Single-script Audio Preprocessor.

Runs the extraction pipeline on ALL files in a specified directory.
Output is saved sequentially as sample_001, sample_002, etc.

Usage:
    1. Edit the DATASET_ROOT variable below.
    2. Run: python run_preprocess.py
"""

import sys
import logging
from pathlib import Path

# ==========================================
# [USER CONFIG]
# ==========================================
DATASET_ROOT = r"C:\Project\kaist\4_week\165.가상공간 환경음 매칭 데이터\01-1.정식개방데이터\Training\01.원천데이터"
OUTPUT_ROOT = "preprocess_output"
# ==========================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("drumgenx")

try:
    from drumgenx.separator import extract_drum_stem
    from drumgenx.detector import detect_onsets
    from drumgenx.slicer import build_kit_from_audio
    from drumgenx.utils import load_audio, ensure_dir
except ImportError:
    print("Error: drumgenx package not found.")
    sys.exit(1)

def process_file(audio_path: Path, output_dir: Path):
    """Process a single file and save to specific output_dir."""
    logger.info(f"=== Processing: {audio_path.name} -> {output_dir.name} ===")
    
    file_dir = ensure_dir(output_dir)
    
    try:
        # 1. Separation
        drums_path = extract_drum_stem(
            audio_path, 
            file_dir / "demucs",
            model="htdemucs",
            device="cuda" if sys.platform != "darwin" else "cpu"
        )
        
        # 2. Load
        y, sr = load_audio(drums_path, sr=44100)
        
        # 3. Detection
        onsets = detect_onsets(y, sr, merge_ms=30, backtrack=True)
        if not onsets:
            logger.warning(f"No onsets in {audio_path.name}")
            return

        # 4. Slicing
        # Save directly to 'kit' inside the sample folder
        kit_dir = file_dir / "kit"
        build_kit_from_audio(
            y, sr, onsets, kit_dir,
            max_duration_s=1.5,
            fade_out_ms=10.0
        )
        logger.info(f"Done: {kit_dir}")
        
    except Exception as e:
        logger.error(f"Failed {audio_path.name}: {e}")

def main():
    root = Path(DATASET_ROOT)
    if not root.exists():
        print(f"Error: Dataset path not found: {root}")
        sys.exit(1)

    print(f"Scanning {root}...")
    extensions = ["*.wav", "*.mp3", "*.m4a", "*.flac"]
    files = []
    for ext in extensions:
        files.extend(root.rglob(ext))
    
    if not files:
        print("No audio files found.")
        sys.exit(1)

    print(f"Found {len(files)} files. Starting processing...")
    
    out_root_path = ensure_dir(Path(OUTPUT_ROOT))
    
    for i, f in enumerate(files, 1):
        # Format: sample_001, sample_002...
        folder_name = f"sample_{i:03d}"
        target_dir = out_root_path / folder_name
        
        print(f"\n[{i}/{len(files)}] {f.name} -> {folder_name}")
        process_file(f, target_dir)

if __name__ == "__main__":
    main()

