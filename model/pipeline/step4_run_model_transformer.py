# pipeline/run_model_transformer.py
from __future__ import annotations

import argparse, json
import os
from pathlib import Path
import logging
import random
import copy

import sys
# Add the project root (or model directory) to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Use the new Transformer runner
try:
    from model.stage4_model_gen.drums_transformer.inference import DrumsTransformerRunner
except ImportError:
    from stage4_model_gen.drums_transformer.inference import DrumsTransformerRunner
import pretty_midi

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
        key = (step_idx, note.pitch)
        if key not in grouped_notes:
            grouped_notes[key] = note
        else:
            if note.velocity > grouped_notes[key].velocity:
                grouped_notes[key] = note
    
    steps_per_bar = steps_per_beat * 4 # usually 16
    
    for (step_idx, pitch), note in sorted(grouped_notes.items()):
        
        # Derive bar/step directly from grid index
        bar = step_idx // steps_per_bar
        step = step_idx % steps_per_bar
        
        # Smart Decision Mapping (Pitch -> Role)
        p = pitch
        role = "FILL" # default fallback
        
        if p in [35, 36]: 
            role = "CORE"
        elif p in [38, 40, 37, 39]: # Snares, Claps
            role = "ACCENT"
        elif p in [42, 44, 46, 51, 59, 53]: # Hats, Rides, Bell
            role = "MOTION"
        elif p in [49, 57, 52, 55]: # Crashes
            role = "ACCENT" # Impacts
        elif p in [41, 43, 45, 47, 48, 50]: 
            role = "FILL"
        elif p in [54, 69, 70]: # Shaker/Tamb
            role = "TEXTURE"
        
        # Decision Output
        evt = {
            "bar": bar,
            "step": step,
            "role": role,
            "confidence": 1.0, 
            "intensity": min(1.0, note.velocity / 127.0),
            "pitch": p # Keep pitch for reference
        }
        events.append(evt)
        
    return events

def calculate_similarity(candidate_events: list, skeleton_events: list) -> float:
    """
    Calculates how well the candidate matches the skeleton.
    Focuses on CORE (Kick) and ACCENT (Snare) timing.
    """
    score = 0.0
    total_weight = 0.0
    
    # Index Skeleton by (bar, step, role)
    skel_map = set()
    for e in skeleton_events:
        # We only care about major structural roles for similarity
        if e['role'] in ['CORE', 'ACCENT']:
            skel_map.add((e['bar'], e['step'], e['role']))
            total_weight += 1.0
            
    if total_weight == 0:
        return 1.0 # No skeleton constraints? Match is perfect.
        
    hits = 0
    for e in candidate_events:
        if (e['bar'], e['step'], e['role']) in skel_map:
            hits += 1
            
    # Normalize
    return hits / total_weight

def merge_events(best_events: list, skeleton_events: list) -> list:
    """
    Enforces Skeleton constraints into the Best Candidate.
    Strategy: 
    1. Keep all Candidate events (they have groove/velocity).
    2. If a Skeleton CORE/ACCENT event is MISSING in Candidate, inject it.
       (We assume the Candidate 'forgot' the structure).
    """
    merged = copy.deepcopy(best_events)
    
    # Create a quick lookup for candidate events
    cand_map = set() # (bar, step, role)
    for e in best_events:
        cand_map.add((e['bar'], e['step'], e['role']))
        
    # Check Skeleton
    for s_evt in skeleton_events:
        # Enforce all structural roles + decorations
        if s_evt['role'] not in ['CORE', 'ACCENT', 'MOTION', 'FILL', 'TEXTURE']:
            continue
            
        key = (s_evt['bar'], s_evt['step'], s_evt['role'])
        if key not in cand_map:
            # Inject missing event
            # Smart Velocity Handling:
            # Skeleton usually produces 0.0-1.0 float. Legacy might be 0-127.
            raw_vel = float(s_evt.get('vel', 0.8))
            if raw_vel > 1.0:
                final_intensity = raw_vel / 127.0
            else:
                final_intensity = raw_vel
            
            # Create injected event
            new_evt = {
                "bar": int(s_evt['bar']),
                "step": int(s_evt['step']),
                "role": s_evt['role'],
                "confidence": 0.9, # Enforced
                "intensity": final_intensity,
                "injected": True
            }
            merged.append(new_evt)
            
    # Sort by time
    merged.sort(key=lambda x: (x['bar'], x['step']))
    return merged

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid_json", required=True)
    ap.add_argument("--skeleton_json", required=False, help="Path to skeleton.json constraints")
    ap.add_argument("--pools_json", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--render", action="store_true", help="Enable audio rendering")
    ap.add_argument("--candidates", type=int, default=4, help="Number of candidates to generate")
    ap.add_argument("--sample_root", default="examples/input_samples")
    
    # Legacy args
    ap.add_argument("--python_path", help="Ignored")
    ap.add_argument("--checkpoint_dir", help="Ignored")
    
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grid = json.loads(Path(args.grid_json).read_text())
    
    skeleton_events = []
    if args.skeleton_json and Path(args.skeleton_json).exists():
        skeleton_events = json.loads(Path(args.skeleton_json).read_text())
        print(f"[Transformer] Loaded {len(skeleton_events)} skeleton events for constraint.")
    
    # Initialize Runner
    print(f"[Transformer] Initializing runner...")
    runner = DrumsTransformerRunner()
    
    sample_map = {k.replace("_POOL", ""): v for k, v in json.loads(Path(args.pools_json).read_text()).items() if k.endswith("_POOL")}
    
    # Generate Candidates
    candidates = []
    import torch
    
    base_seed = args.seed
    
    print(f"[Transformer] Generating {args.candidates} candidates...")
    
    for i in range(args.candidates):
        # Vary seed for each candidate
        curr_seed = base_seed + i
        torch.manual_seed(curr_seed)
        
        # Generate tokens
        tokens = runner.generate_beat(max_tokens=1024)
        
        # Save temp MIDI to parse
        tmp_midi = out_dir / f"temp_cand_{i}.mid"
        runner.tokens_to_midi(tokens, str(tmp_midi))
        
        # Parse to events
        evts = midi_to_events(tmp_midi, grid, sample_map)
        candidates.append((curr_seed, evts, tmp_midi))
        
    # Select Best matched to Skeleton
    best_cand = candidates[0]
    best_score = -1.0
    
    if not skeleton_events:
        # No skeleton? Just pick the first (seed match)
        best_cand = candidates[0]
        print("[Transformer] No skeleton provided. Using first candidate.")
    else:
        for seed, evts, midi_path in candidates:
            score = calculate_similarity(evts, skeleton_events)
            print(f" - Candidate Seed {seed}: Similarity {score:.2f}")
            if score > best_score:
                best_score = score
                best_cand = (seed, evts, midi_path)
        
        print(f"[Transformer] Selected Seed {best_cand[0]} with Score {best_score:.2f}")

    # Merge/Enforce
    final_events = best_cand[1]
    if skeleton_events:
        final_events = merge_events(best_cand[1], skeleton_events)
        print(f"[Transformer] Merged with Skeleton (Original: {len(best_cand[1])}, Final: {len(final_events)})")

    # Output Final Result
    vid = 1
    out_events = out_dir / f"event_grid_transformer_{vid}.json"
    out_events.write_text(json.dumps(final_events, indent=2, ensure_ascii=False))
    
    # Also copy/rename the best MIDI for reference
    best_midi_src = best_cand[2]
    out_midi = out_dir / f"transformer_output_{vid}.mid"
    if best_midi_src.exists():
        # We might want to regenerate MIDI from final_events if we injected notes?
        # But 'midi_to_events' is lossy (quantization). 
        # Ideally, we should add notes to the MIDI file too if we want the MIDI to match.
        # For now, let's just keep the Transformer's original MIDI as the "Raw" output, 
        # and the JSON as the "Pipeline" output which Stage 5 will use.
        # Stage 5 generates audio from JSON, so the JSON being correct is what matters.
        import shutil
        shutil.copy(best_midi_src, out_midi)
    
    # Clean up temp files
    for _, _, mp in candidates:
        if mp.exists() and mp != best_midi_src:
            mp.unlink()

    # Audio Render (Optional)
    out_wav = out_dir / f"render_transformer_{vid}.wav"
    if args.render:
        try:
            from stage3_beat_grid.test_audio_render.render import render_events
            render_events(
                grid_json=grid,
                events=final_events,
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

if __name__ == "__main__":
    main()