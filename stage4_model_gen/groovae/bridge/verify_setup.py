# stage4_model_gen/groovae/verify_setup.py
import argparse
import sys
import os
from note_seq.protobuf import music_pb2

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

try:
    from stage4_model_gen.groovae.bridge.run_groovae_subprocess import GrooVAESubprocessRunner
except ImportError:
    print("Could not import GrooVAESubprocessRunner. Make sure you are at project root or PYTHONPATH is set.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Verify GrooVAE Dual Environment Setup")
    parser.add_argument("--python_path", required=True, help="Path to the python executable of the magenta environment")
    parser.add_argument("--checkpoint_dir", required=True, help="Path to checkpoint directory")
    
    args = parser.parse_args()
    
    # Create a dummy NoteSequence
    print("Creating dummy input NoteSequence...")
    ns = music_pb2.NoteSequence()
    ns.tempos.add(qpm=120)
    ns.total_time = 4.0 # 2 bars at 120bpm = 4.0s
    # Quantized sequence is required for most MusicVAE models
    ns.quantization_info.steps_per_quarter = 4
    
    import note_seq
    # Use standard quantizer

    
    # Add a simple kick drum note
    note = ns.notes.add()
    note.pitch = 36
    note.velocity = 80
    note.start_time = 0.0
    note.end_time = 0.1
    note.is_drum = True
    
    # Quantize
    ns = note_seq.quantize_note_sequence(ns, 4)
    
    # Initialize Runner
    print(f"Initializing Runner with python: {args.python_path}")
    runner = GrooVAESubprocessRunner(
        python_path=args.python_path,
        checkpoint_dir=args.checkpoint_dir
    )
    
    # Run
    print("Running GrooVAE subprocess...")
    import time
    start_t = time.time()
    try:
        # Note: This might fail if the model checkpoint is invalid or model logic fails, 
        # but the subprocess call itself should work (or return a specific error).
        out_ns = runner.run(ns)
        end_t = time.time()
        duration = end_t - start_t
        print("Success! Got output NoteSequence.")
        print(f"Output notes count: {len(out_ns.notes)}")
        print(f"Inference Time: {duration:.4f} seconds")
    except Exception as e:
        print(f"Verification Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
