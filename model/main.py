import subprocess
import argparse
import sys
import os
import time
from pathlib import Path

# Setup paths
MODEL_DIR = Path(__file__).parent.resolve() # /home/dh/soundroutine/model
PROJECT_ROOT = MODEL_DIR.parent.resolve() # /home/dh/soundroutine
PIPELINE_DIR = MODEL_DIR / "pipeline"

def run_step(step_name, cmd_args):
    print(f"\n[pipeline] Running {step_name} ...")
    cmd = [sys.executable, str(PIPELINE_DIR / step_name)] + cmd_args
    print(f"[cmd] {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd, cwd=PROJECT_ROOT)
        print(f"[pipeline] {step_name} Success.\n")
    except subprocess.CalledProcessError as e:
        print(f"[pipeline] {step_name} Failed!")
        sys.exit(e.returncode)

def get_latest_file(directory: Path, pattern: str) -> Path:
    files = list(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matching {pattern} in {directory}")
    
    def extract_version(p: Path) -> int:
        try:
            # Pattern {name}_{ver}.{ext}
            return int(p.stem.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return 0
            
    return sorted(files, key=extract_version)[-1]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", type=str, required=True, help="Raw audio input directory")
    p.add_argument("--project_name", type=str, default="project_001")
    p.add_argument("--bpm", type=float, default=120.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--style", type=str, default="auto", help="Music style (rock, house, funk, rnb, auto, etc)")
    args = p.parse_args()
    
    start_time = time.time()
    
    # --- Smart Style Selection Logic ---
    def suggest_style_by_bpm(bpm: float) -> str:
        """Recommend a style based on BPM ranges."""
        import random
        b = float(bpm)
        
        # 1. Slow (< 100): HipHop, Trap, R&B, Reggae
        if b < 100:
            candidates = ["hiphop", "trap", "rnb", "rock"]
            weights    = [0.4,      0.3,    0.2,   0.1]
            return random.choices(candidates, weights=weights, k=1)[0]
            
        # 2. Mid (100-115): Funk, Rock, Glitch? (Glitch not impl yet)
        elif b < 115:
            candidates = ["funk", "rock", "hiphop", "house"] # Slow house?
            weights    = [0.4,    0.3,    0.2,      0.1]
            return random.choices(candidates, weights=weights, k=1)[0]
            
        # 3. Fast (115-130): House, Techno, Disco
        elif b < 130:
            candidates = ["house", "techno", "funk", "rock"]
            weights    = [0.4,     0.3,      0.2,    0.1]
            return random.choices(candidates, weights=weights, k=1)[0]
            
        # 4. Very Fast (130+): DnB, Techno
        else:
            candidates = ["dnb", "techno", "trap"] # Fast trap?
            weights    = [0.5,   0.3,      0.2]
            return random.choices(candidates, weights=weights, k=1)[0]

    # Resolving Style
    chosen_style = args.style.lower()
    
    if chosen_style in ["auto", "random"]:
        print(f"[pipeline] Style '{chosen_style}' requested. Detecting best fit for {args.bpm} BPM...")
        chosen_style = suggest_style_by_bpm(args.bpm)
        print(f"[pipeline] ==> Smart Recommendation: {chosen_style.upper()}")
        
    else:
        print(f"\n[pipeline] Style explicitly selected: {chosen_style.upper()}")
    
    # 0. Output Setup
    output_root = PROJECT_ROOT / "outs" / args.project_name
    output_root.mkdir(parents=True, exist_ok=True)
    
    dirs = {
        "s1": output_root / "1_preprocess",
        "s2": output_root / "2_role",
        "s3": output_root / "3_grid",
        "s4": output_root / "4_model_gen",
        "s5": output_root / "5_midi",
        "s6": output_root / "6_editor",
        "s7": output_root / "7_final",
    }
    
    # Stage 1: Preprocess
    run_step("step1_run_preprocess.py", [
        "--input_dir", str(args.input_dir),
        "--out_dir", str(dirs["s1"])
    ])
    
    # Find latest stage1 output directory to avoid re-processing old runs
    # Pattern: stage1_YYYYMMDD_HHMMSS
    stage1_dirs = sorted(list(dirs["s1"].glob("stage1_*")))
    if not stage1_dirs:
        print("[pipeline] Error: No Stage 1 output found!")
        sys.exit(1)
    latest_s1_dir = stage1_dirs[-1]
    print(f"[pipeline] Using latest Stage 1 output: {latest_s1_dir}")
    
    # Stage 2: Role Assignment
    run_step("step2_run_role_assignment.py", [
        "--input_dir", str(latest_s1_dir),
        "--out_dir", str(dirs["s2"]),
        "--limit", "0" # Process all
    ])
    
    # Find latest pools.json
    pools_json = get_latest_file(dirs["s2"], "role_pools_*.json")
    
    # Stage 3: Grid Setup
    run_step("step3_run_grid_and_skeleton.py", [
        "--out_dir", str(dirs["s3"]),
        "--bpm", str(args.bpm),
        "--style", str(chosen_style),
        "--seed", str(args.seed),
        "--pools_json", str(pools_json)
    ])
    
    # Find generated files
    grid_json = get_latest_file(dirs["s3"], "grid_*.json")
    skeleton_json = get_latest_file(dirs["s3"], "skeleton_*.json")
    
    # Stage 4: Model Transformer (Generator)
    run_step("step4_run_model_transformer.py", [
        "--grid_json", str(grid_json),
        "--skeleton_json", str(skeleton_json),
        "--pools_json", str(pools_json),
        "--out_dir", str(dirs["s4"]),
        "--seed", str(args.seed),
        "--sample_root", str(dirs["s1"])
    ])
    
    # Find transformer outputs
    notes_json = get_latest_file(dirs["s4"], "event_grid_transformer_*.json")

    # Stage 5: Note & MIDI (Mapping Back)
    run_step("step5_run_note_and_midi.py", [
        "--grid_json", str(grid_json),
        "--notes_json", str(notes_json),
        "--pools_json", str(pools_json),
        "--out_dir", str(dirs["s5"]),
        "--seed", str(args.seed),
        "--progressive", "1",      # Explicitly enable progressive
        "--repeat_full", "8"       # Increase loop count to meet >40 bars requirement (4*4 + 4*8 = 16+32 = 48 bars)
    ])
    
    final_events_json = get_latest_file(dirs["s5"], "event_grid_*.json")
    # Check if updated grid file exists in s5
    try:
        s5_grid = get_latest_file(dirs["s5"], "grid_*.json")
        grid_json = s5_grid
        print(f"[pipeline] Detected updated grid in Stage 5: {grid_json}")
    except FileNotFoundError:
        pass
    
    # Stage 6: Editor (Optimization/Export)
    run_step("step6_run_editor.py", [
        "--grid_json", str(grid_json),
        "--event_grid", str(final_events_json),
        "--out_dir", str(dirs["s6"]),
        "--seed", str(args.seed),
        "--sample_root", str(dirs["s1"]),
        "--render_preview", "1"
    ])
    
    editor_events_json = get_latest_file(dirs["s6"], "event_grid_*.json")

    # Stage 7: Final Render
    run_step("step7_run_render_final.py", [
        "--grid_json", str(grid_json),
        "--event_grid_json", str(editor_events_json),
        "--sample_root", str(dirs["s1"]),
        "--out_dir", str(dirs["s7"]),
        "--name", f"{args.project_name}_final"
    ])
    
    print("\n[pipeline] ALL DONE!")
    print(f"Final Output: {dirs['s7']}/{args.project_name}_final.mp3")
    
    elapsed = time.time() - start_time
    print(f"[pipeline] Total execution time: {elapsed:.2f} seconds")

if __name__ == "__main__":
    main()
