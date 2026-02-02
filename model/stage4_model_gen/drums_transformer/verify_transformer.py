
import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

logging.basicConfig(level=logging.INFO)

def main():
    print("=== Verifying Drums Transformer Setup ===")
    
    try:
        from model.stage4_model_gen.drums_transformer.inference import DrumsTransformerRunner
    except ImportError as e:
        print(f"ImportError: {e}")
        # Try relative import if running from module
        sys.exit(1)

    try:
        runner = DrumsTransformerRunner()
        print("Runner initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize runner: {e}")
        sys.exit(1)

    print("Generating beat...")
    try:
        tokens = runner.generate_beat(max_tokens=256)
        print(f"Generated {len(tokens)} tokens.")
    except Exception as e:
        print(f"Generation failed: {e}")
        sys.exit(1)

    output_path = "test_drum_out" # TMIDIX adds .mid
    print(f"Saving to {output_path}...")
    try:
        final_path = runner.tokens_to_midi(tokens, output_path)
        print(f"Saved MIDI to {final_path}")
    except Exception as e:
        print(f"MIDI conversion failed: {e}")
        sys.exit(1)

    print("=== Verification PASSED ===")

if __name__ == "__main__":
    main()
