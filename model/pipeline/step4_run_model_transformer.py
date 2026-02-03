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
    
    for note in notes:
        # Quantize to nearest step index
        step_idx = round(note.start / seconds_per_step)
        quantized_start = step_idx * seconds_per_step
        
        # Calculate deviation in milliseconds
        offset_sec = note.start - quantized_start
        micro_offset_ms = int(offset_sec * 1000)
        
        # General MIDI Mapping
        role = "percussion"
        # Standard Drum Map
        # 35,36: Kick
        # 38,40: Snare
        # 41,43: Low Tom
        # 42,44: HiHat (Closed/Pedal)
        # 46: HiHat Open
        # 49,57,51,59: Cymbals
        p = note.pitch
        if p in [35, 36]: role = "kick"
        elif p in [38, 40]: role = "snare"
        elif p in [42, 44]: role = "hat" # Closed
        elif p == 46: role = "hat" # Open -> maybe map to same role but different sample if supported
        elif p in [49, 57, 51, 59, 52, 55]: role = "cymbal"
        elif p in [41, 43, 45, 47, 48, 50]: role = "tom"
        
        evt = {
            "start": note.start,
            "end": note.end,
            "velocity": note.velocity,
            "pitch": note.pitch,
            "role": role,
            "is_drum": True,
            "offset": 0, # Legacy field, can be kept as 0 or step offset
            "micro_offset_ms": micro_offset_ms
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