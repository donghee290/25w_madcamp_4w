
import subprocess
import argparse
import sys
import os
from pathlib import Path

# Setup paths
BASE_DIR = Path(__file__).parent.parent.resolve() # /home/dh/soundroutine/model
PIPELINE_DIR = BASE_DIR / "pipeline"

def run_step(step_name, cmd_args):
    print(f"\n[pipeline] Running {step_name} ...")
    cmd = [sys.executable, str(PIPELINE_DIR / step_name)] + cmd_args
    print(f"[cmd] {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd, cwd=BASE_DIR)
        print(f"[pipeline] {step_name} Success.\n")
    except subprocess.CalledProcessError as e:
        print(f"[pipeline] {step_name} Failed!")
        sys.exit(e.returncode)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", type=str, required=True, help="Raw audio input directory")
    p.add_argument("--project_name", type=str, default="project_001")
    p.add_argument("--bpm", type=float, default=120.0)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    
    # 0. Output Setup
    output_root = BASE_DIR / "outs" / args.project_name
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
    
    # Stage 2: Role Assignment
    run_step("step2_run_role_assignment.py", [
        "--input_dir", str(dirs["s1"]),
        "--out_dir", str(dirs["s2"]),
        "--limit", "0" # Process all
    ])
    
    # Find latest pools.json
    pools_json = sorted(list(dirs["s2"].glob("role_pools_*.json")))[-1]
    
    # Stage 3: Grid & Skeleton
    run_step("step3_run_grid_and_skeleton.py", [
        "--pools_json", str(pools_json),
        "--out_dir", str(dirs["s3"]),
        "--bpm", str(args.bpm),
        "--seed", str(args.seed),
        "--sample_root", str(dirs["s1"]) # Render needs samples
    ])
    
    # Find generated files
    grid_json = sorted(list(dirs["s3"].glob("grid_*.json")))[-1]
    event_grid_json = sorted(list(dirs["s3"].glob("event_grid_*.json")))[-1]
    
    # Stage 4: Model Transformer
    run_step("step4_run_model_transformer.py", [
        "--grid_json", str(grid_json),
        "--events_json", str(event_grid_json),
        "--pools_json", str(pools_json),
        "--out_dir", str(dirs["s4"]),
        "--seed", str(args.seed),
        "--sample_root", str(dirs["s1"])
    ])
    
    # Find transformer outputs
    notes_json = sorted(list(dirs["s4"].glob("event_grid_transformer_*.json")))[-1]

    # Stage 5: Note & MIDI (Mapping Back)
    run_step("step5_run_note_and_midi.py", [
        "--grid_json", str(grid_json),
        "--notes_json", str(notes_json),
        "--pools_json", str(pools_json),
        "--out_dir", str(dirs["s5"]),
        "--seed", str(args.seed)
    ])
    
    final_events_json = sorted(list(dirs["s5"].glob("event_grid_*.json")))[-1]
    
    # Stage 6: Editor (Optimization/Export)
    run_step("step6_run_editor.py", [
        "--grid_json", str(grid_json),
        "--event_grid", str(final_events_json),
        "--out_dir", str(dirs["s6"]),
        "--seed", str(args.seed),
        "--sample_root", str(dirs["s1"]),
        "--render_preview", "1"
    ])
    
    editor_events_json = sorted(list(dirs["s6"].glob("event_grid_*.json")))[-1]

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

if __name__ == "__main__":
    main()
