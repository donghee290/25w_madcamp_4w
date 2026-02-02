"""Experimental Script to Compare Classifiers and Generate Report."""

import argparse
from pathlib import Path
import librosa
import numpy as np
import json

from stage1_drumgenx.features import extract_dsp_features
from stage1_drumgenx.scoring import calculate_role_scores, get_best_role, DrumRole
from stage1_drumgenx.utils import load_audio

def analyze_kit(kit_dir: Path):
    print(f"Analyzing kit: {kit_dir}")
    
    results = []
    
    # Iterate over all wav files recursively
    for wav_path in kit_dir.rglob("*.wav"):
        try:
            y, sr = load_audio(wav_path)
            
            # DSP Features
            feats = extract_dsp_features(y, sr)
            
            # Role Scores
            scores = calculate_role_scores(feats)
            best_role, best_score = get_best_role(scores)
            
            # Original folder name as "Ground Truth" proxy (from previous classifier)
            original_class = wav_path.parent.name
            
            results.append({
                "file": wav_path.name,
                "original_class": original_class,
                "new_role": best_role.value,
                "score": round(best_score, 3),
                "features": {k: round(v, 3) for k, v in feats.items()},
                "all_scores": {k.value: round(v, 3) for k, v in scores.items()}
            })
            
            print(f"[{original_class}] {wav_path.name} -> {best_role.value} ({best_score:.2f})")
            
        except Exception as e:
            print(f"Error processing {wav_path.name}: {e}")

    # Summary
    print("\n=== Summary ===")
    from collections import Counter
    role_counts = Counter(r["new_role"] for r in results)
    for role, count in role_counts.items():
        print(f"{role}: {count}")
        
    # Save detailed report
    report_path = kit_dir / "analysis_comparison.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kit_dir", type=Path)
    args = parser.parse_args()
    
    analyze_kit(args.kit_dir)
