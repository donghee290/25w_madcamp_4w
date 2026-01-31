"""Single-script Audio Preprocessor.

Runs Extraction only (NO Classification):
1. Demucs (Separation)
2. Onset Detection
3. Slicing -> Save Raw Slices

Usage:
    1. Edit the DATASET_ROOT variable below.
    2. Run: python run_preprocess.py
"""

import sys
import logging
from pathlib import Path
import numpy as np

# ==========================================
# [USER CONFIG]
# ==========================================
# Put your audio files in this folder to test!
DATASET_ROOT = r"C:\Project\kaist\4_week\165.가상공간 환경음 매칭 데이터\01-1.정식개방데이터\Training\01.원천데이터\TS_1.공간_1.현실 공간_환경_002.병원_wav"
OUTPUT_ROOT = "preprocess_output_raw"
# ==========================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("drumgenx")

try:
    from drumgenx.separator import extract_drum_stem
    from drumgenx.detector import detect_onsets
    from drumgenx.slicer import slice_hits, normalize_hit
    from drumgenx.utils import load_audio, save_audio, ensure_dir
except ImportError:
    print("Error: drumgenx package not found.")
    sys.exit(1)

def process_file(audio_path: Path, output_dir: Path):
    """Process a single file: Separate -> Detect -> Slice -> Save Raw."""
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

        # 4. Slicing (Raw)
        hits = slice_hits(
            y, sr, onsets, 
            max_duration_s=1.5,
            fade_out_ms=10.0
        )
        
        if not hits:
            logger.warning("No hits sliced.")
            return

        # 5. Save Raw Slices (Dummy Data)
        slices_dir = ensure_dir(file_dir / "slices")
        logger.info(f"Saving {len(hits)} raw slices...")
        
        for i, hit in enumerate(hits):
            # Normalize before saving? Usually good practice.
            hit = normalize_hit(hit)
            
            fname = f"slice_{i:04d}.wav"
            save_audio(slices_dir / fname, hit, sr)
            
        logger.info(f"Done: {slices_dir}")
        
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

