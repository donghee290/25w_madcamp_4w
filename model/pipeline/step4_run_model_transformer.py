# pipeline/run_model_transformer.py
from __future__ import annotations

import argparse, json
import os
from pathlib import Path
import logging

import sys
# Add the project root (or model directory) to sys.path
# Script is in model/pipeline/run_model_transformer.py
# We want to import stage4_model_gen which is in model/stage4_model_gen
# So we add "../" (model dir) to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Use the new Transformer runner
try:
    from model.stage4_model_gen.drums_transformer.inference import DrumsTransformerRunner
except ImportError:
    # If running from inside model dir
    from stage4_model_gen.drums_transformer.inference import DrumsTransformerRunner
import pretty_midi
import note_seq # Import note_seq to use some utilities if needed, or we just write pure midi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def midi_to_events(midi_path: str, grid: dict, sample_map: dict) -> list:
    """
    Converts MIDI file to the pipeline's event format with micro-timing.
    """
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    events = []
    
    # Get BPM from grid
    bpm = grid.get("bpm", 120)
    # 60 / BPM = seconds per beat
    # We want to find the nearest "16th note" or "grid step"
    # Typically grid is 4 steps per beat (16th notes).
    steps_per_beat = 4
    seconds_per_step = (60.0 / bpm) / steps_per_beat
    
    # Merge all notes
    notes = []
    for inst in pm.instruments:
        notes.extend(inst.notes)
    
    notes.sort(key=lambda x: x.start)
    
    grouped_notes = {}
    
    for note in notes:
        # Quantize to nearest step index
        step_idx = round(note.start / seconds_per_step)
        quantized_start = step_idx * seconds_per_step
        key = (step_idx, note.pitch)
        if key not in grouped_notes:
            grouped_notes[key] = note
        else:
            # If multiple notes at same step/pitch, take the one with higher velocity
            if note.velocity > grouped_notes[key].velocity:
                grouped_notes[key] = note
    
    # Convert distinct notes to events
    # Output Schema: bar, step, role, confidence, intensity
    # NO time, offset, start_sec
    steps_per_bar = steps_per_beat * 4 # usually 16
    
    for (step_idx, pitch), note in sorted(grouped_notes.items()):
        
        # Derive bar/step directly from grid index
        bar = step_idx // steps_per_bar
        step = step_idx % steps_per_bar
        
        # General MIDI Mapping
        role = "percussion"
        # Enhanced MIDI Mapping for "Smart Decision"
        # 35,36 (Kick) -> CORE
        # 38,40 (Snare) -> ACCENT
        # 42,44,46 (Hats) -> MOTION
        # 51,59 (Ride) -> MOTION
        # 49,57,52,55 (Crash/Splash) -> ACCENT (Impacts)
        # 41,43,45,47,48,50 (Toms) -> FILL
        # 54 (Tambourine), 69 (Cabasa), 70 (Maracas) -> MOTION/TEXTURE
        # Others -> FILL/TEXTURE
        
        p = pitch
        role = "percussion" # default
        
        if p in [35, 36]: 
            role = "CORE"
        elif p in [38, 40, 37, 39]: # Snares, Claps(39)
            role = "ACCENT"
        elif p in [42, 44, 46]: 
            role = "MOTION"
        elif p in [51, 59, 53]: # Rides, Bell
            role = "MOTION" # Map Ride to MOTION layer
        elif p in [49, 57, 52, 55]: # Crashes
            role = "ACCENT" # Map Crash to ACCENT layer (strong impact)
        elif p in [41, 43, 45, 47, 48, 50]: 
            role = "FILL"
        elif p in [54, 69, 70]: # Shaker/Tamb
            role = "TEXTURE" # Map high-freq loops to TEXTURE/MOTION
        else:
            role = "FILL" # Map unknown percs to FILL
        
        # Decision Output
        evt = {
            "bar": bar,
            "step": step,
            "role": role,
            "confidence": 1.0, # Model 'chose' this token, so high confidence
            "intensity": min(1.0, note.velocity / 127.0)
        }
        events.append(evt)
        
    return events

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid_json", required=True)
    ap.add_argument("--events_json", required=True) # Used for length/context
    ap.add_argument("--pools_json", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--render", action="store_true", help="Enable audio rendering")
    ap.add_argument("--sample_root", default="examples/input_samples")
    
    # Arguments compatible with old interface
    ap.add_argument("--python_path", help="Ignored")
    ap.add_argument("--checkpoint_dir", help="Ignored")
    
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grid = json.loads(Path(args.grid_json).read_text())
    
    # Initialize Runner
    print(f"[Transformer] Initializing runner...")
    runner = DrumsTransformerRunner()
    
    # Generate
    print(f"[Transformer] Generating beat... (seed={args.seed})")
    import torch
    torch.manual_seed(args.seed)
    
    # Generate tokens
    tokens = runner.generate_beat(max_tokens=512)
    
    # Convert to MIDI
    vid = 1 # version id
    out_midi = out_dir / f"transformer_output_{vid}.mid"
    runner.tokens_to_midi(tokens, str(out_midi))
    
    # Convert MIDI to Events (for pipeline)
    sample_map = {k.replace("_POOL", ""): v for k, v in json.loads(Path(args.pools_json).read_text()).items() if k.endswith("_POOL")}
    events_out = midi_to_events(out_midi, grid, sample_map)

    # Save Events
    out_events = out_dir / f"event_grid_transformer_{vid}.json"
    out_events.write_text(json.dumps(events_out, indent=2, ensure_ascii=False))

    # Audio Render (Optional)
    out_wav = out_dir / f"render_transformer_{vid}.wav"
    if args.render:
        try:
            from stage3_beat_grid.test_audio_render.render import render_events
            render_events(
                grid_json=grid,
                events=events_out,
                sample_root=Path(args.sample_root),
                out_wav=out_wav,
                target_sr=44100,
            )
        except ImportError:
            print("[Warning] Could not import render_events, skipping audio render.")
        except Exception as e:
            print(f"[Warning] Render failed: {e}")

    print("[DONE] Transformer stage complete")
    print(" - events:", out_events)
    print(" - midi:", out_midi)
    print(" - wav:", out_wav)

if __name__ == "__main__":
    main()