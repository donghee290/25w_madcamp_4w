# stage4_model_gen/groovae/groovae_exec.py
import argparse
import sys
import os
import pickle

# Add project root to path so we can import modules if needed
# Assuming this script is at <root>/stage4_model_gen/groovae/bridge/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

# --- CRITICAL: TENSORFLOW SETUP BEFORE IMPORTS ---
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_BLOCKTIME"] = "0"

print("DEBUG: Initializing TensorFlow in executor...")
import tensorflow.compat.v1 as tf
try:
    tf.disable_eager_execution()
    print("DEBUG: Eager execution disabled.")
except Exception as e:
    print(f"WARNING: Failed to disable eager execution: {e}")

# Monkey Patch Session to force single-threading (Deadlock Fix)
_OriginalSession = tf.Session
def _PatchedSession(target='', graph=None, config=None):
    if config is None:
        config = tf.ConfigProto()
    # Force single threading
    config.inter_op_parallelism_threads = 1
    config.intra_op_parallelism_threads = 1
    config.allow_soft_placement = True
    print("DEBUG: Creating Patched Session (Thread-safe)")
    return _OriginalSession(target=target, graph=graph, config=config)
tf.Session = _PatchedSession
# -------------------------------------------------

try:
    from stage4_model_gen.groovae.runner import GrooVAERunner, GrooVAEModelConfig
    from note_seq.protobuf import music_pb2
except ImportError as e:
    print(f"ImportError in groovae_exec: {e}", file=sys.stderr)
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="GrooVAE Executor for Subprocess")
    parser.add_argument("--input_path", required=True, help="Path to input serialized NoteSequence")
    parser.add_argument("--output_path", required=True, help="Path to save output serialized NoteSequence")
    parser.add_argument("--checkpoint_dir", required=True, help="Path to checkpoint directory")
    parser.add_argument("--config_name", default="groovae_2bar_humanize", help="Model config name")
    parser.add_argument("--temperature", type=float, default=1.0, help="Sampling temperature")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    
    args = parser.parse_args()

    # 1. Load Input
    print(f"Loading input from {args.input_path}...")
    try:
        with open(args.input_path, "rb") as f:
            ns_str = f.read()
            ns = music_pb2.NoteSequence.FromString(ns_str)
    except Exception as e:
        print(f"Failed to load input NoteSequence: {e}", file=sys.stderr)
        sys.exit(2)

    # 2. Configure Model
    model_cfg = GrooVAEModelConfig(
        config_name=args.config_name,
        checkpoint_dir=args.checkpoint_dir,
        temperature=args.temperature,
        trim_to_input_length=True 
    )

    # 3. Run GrooVAE
    print("Initializing GrooVAERunner...")
    try:
        runner = GrooVAERunner(seed=args.seed, model_cfg=model_cfg) # Pass seed here
        print("Running model execution...")
        out_ns = runner.run(ns)
    except Exception as e:
        print(f"Error during GrooVAE execution: {e}", file=sys.stderr)
         # Detailed traceback might be helpful
        import traceback
        traceback.print_exc()
        sys.exit(3)

    # 4. Save Output
    print(f"Saving output to {args.output_path}...")
    try:
        with open(args.output_path, "wb") as f:
            f.write(out_ns.SerializeToString())
    except Exception as e:
        print(f"Failed to save output NoteSequence: {e}", file=sys.stderr)
        sys.exit(4)

    print("GrooVAE execution completed successfully.")

if __name__ == "__main__":
    main()
