
import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


import os
import torch
import torch.nn.functional as F
from huggingface_hub import hf_hub_download
import logging
import sys

# Add current directory to path to allow importing sibling modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from .x_transformer_1_23_2 import TransformerWrapper, Decoder, AutoregressiveWrapper
    from . import TMIDIX
except ImportError:
    # Fallback for direct execution
    import x_transformer_1_23_2
    from x_transformer_1_23_2 import TransformerWrapper, Decoder, AutoregressiveWrapper
    import TMIDIX

logger = logging.getLogger(__name__)

class DrumsTransformerRunner:
    """
    Runner for 'Ultimate Drums Transformer' (Custom Architecture).
    """
    def __init__(self, device: str = None):
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Initializing DrumsTransformerRunner on {self.device}")
        
        # Model Constants (from original script)
        self.SEQ_LEN = 8192
        self.PAD_IDX = 393
        self.repo_id = 'asigalov61/Ultimate-Drums-Transformer'
        self.filename = 'Ultimate_Drums_Transformer_Small_Trained_Model_VER4_VEL_4L_14597_steps_0.3894_loss_0.876_acc.pth'
        
        # 1. Download Model
        self._download_model()

        # 2. Instantiate Model Architecture
        self.model = TransformerWrapper(
            num_tokens = self.PAD_IDX+1,
            max_seq_len = self.SEQ_LEN,
            attn_layers = Decoder(dim = 1024, depth = 4, heads = 16, attn_flash = True)
        )
        self.model = AutoregressiveWrapper(self.model, ignore_index = self.PAD_IDX, pad_value=self.PAD_IDX)
        
        # 3. Load Weights
        logger.info("Loading state dict...")
        model_path = os.path.join(current_dir, "models", self.filename)
        # map_location ensures we can load on CPU if CUDA is not available
        state_dict = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()
        
        # Automatic Mixed Precision
        self.ctx = torch.amp.autocast(device_type="cuda" if "cuda" in self.device else "cpu", dtype=torch.float16)
        logger.info("Model loaded successfully.")

    def _download_model(self):
        models_dir = os.path.join(current_dir, "models")
        os.makedirs(models_dir, exist_ok=True)
        local_path = os.path.join(models_dir, self.filename)
        
        if not os.path.exists(local_path):
            logger.info(f"Downloading model {self.filename} from HF...")
            hf_hub_download(
                repo_id=self.repo_id,
                filename=self.filename,
                local_dir=models_dir,
                local_dir_use_symlinks=False
            )
        else:
            logger.info(f"Model found at {local_path}")

    def generate_beat(self, max_tokens=512, temperature=0.9, start_token=291):
        """
        Generates a drum beat.
        Default start_token=291 (MIDI 35 Acoustic Bass Drum).
        This forces the model to start with a Kick, ensuring a strong downbeat.
        """
        outy = [start_token]
        
        inp = torch.tensor([outy], dtype=torch.long).to(self.device)
        
        logger.info(f"Generating beat with seed token {start_token} (Kick)...")
        
        with self.ctx:
            with torch.no_grad():
                out = self.model.generate(
                    inp,
                    max_tokens,
                    temperature=temperature,
                    return_prime=True, # Include input in output
                    verbose=False
                )
        
        generated_seq = out[0].tolist()
        return generated_seq

    def tokens_to_midi(self, tokens, output_path):
        """
        Decodes tokens to MIDI file using the logic from 'ultimate_drums_transformer_velocity.py'.
        """
        song = tokens
        song_f = []
        
        time = 0
        dtime = 0
        dur = 32 # Default duration
        vel = 90
        pitch = 0
        
        # Defaults for drum map
        channel = 9 # MIDI Channel 10 (0-indexed 9)
        patch = 0 # Kit
        
        # Decoding Loop
        for ss in song:
            # 0-127: Time Shift (Wait)
            if 0 < ss < 128:
                time += ss * 32
                dtime = time
            
            # 128-255: Delta Time? or Note On?
            # Original script: dtime += (ss-128) * 32
            # Wait, dtime is set to time above. 
            # In the loop: 
            #   song_f.append(['note', ptime, dur, 0, random.choice([60,62,64]), vel, patch]) if 0 < ss < 128??
            #   No, looking at original script lines 267-291:
            #   The original script generates a MELODY + DRUMS.
            #   We only care about DRUM tokens if the model generates them.
            #   The drum tokens seem to be:
            #     256 <= ss < 384: Pitch = ss-256
            #     384 <= ss < 393: Velocity = (ss-384)*15
            #     Write Note: song_f.append(['note', dtime, dur, 9, pitch, vel, 128])
            
            # Let's revisit the exact logic for DRUMS.
            
            if 128 <= ss < 256:
                dtime += (ss-128) * 32
                
            if 256 <= ss < 384:
                pitch = (ss-256)
                
            if 384 <= ss < 393:
                vel = (ss-384) * 15
                # Note event: [type, start, dur, channel, pitch, vel, patch]
                song_f.append(['note', dtime, dur, 9, pitch, vel, 0])
        
        # Convert to MIDI using TMIDIX
        # Prepare patches list (channel 10 usually ignores patch, but for correctness)
        patches = [0] * 16
        
        logger.info(f"Converting {len(song_f)} notes to MIDI...")
        
        stats = TMIDIX.Tegridy_ms_SONG_to_MIDI_Converter(
            song_f,
            output_signature = 'SoundRoutine AI Drums',
            output_file_name = output_path, # TMIDIX adds .mid extension automatically? Check TMIDIX.
            track_name='Drum Track',
            list_of_MIDI_patches=patches
        )
        
        # Clean up double extension if TMIDIX added it
        if os.path.exists(output_path + ".mid"):
            os.rename(output_path + ".mid", output_path)
            
        return output_path

