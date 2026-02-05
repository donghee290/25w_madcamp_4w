import logging
import os
from pathlib import Path
from typing import Dict, Optional

from .state_manager import StateManager

logger = logging.getLogger(__name__)

class AudioService:
    def __init__(self, outs_root: Path, state_manager: StateManager):
        self.outs_root = outs_root
        self.state_manager = state_manager

    def convert_output(self, beat_name: str, kind: str) -> Path:
        """
        Returns the path to the requested audio format.
        Used for on-demand download/preview.
        valid kinds: mp3, wav, flac, ogg, m4a
        """
        state = self.state_manager.get_state(beat_name)
        
        # 1. Check state
        key = f"latest_{kind}"
        if state.get(key):
            p = Path(state[key])
            if p.exists():
                return p
            
            # Fallback: Check sibling files
            if p.parent.exists():
                 candidates = list(p.parent.glob(f"*{kind}"))
                 if candidates:
                     return candidates[0]
                 if kind == "mp3":
                      candidates_wav = list(p.parent.glob("*.wav"))
                      if candidates_wav:
                          return candidates_wav[0]

        try:
            latest = self.get_latest_output(beat_name)
            path_str = latest.get(f"{kind}_path")
            if path_str:
                p = Path(path_str)
                if p.exists():
                    return p
        except FileNotFoundError:
            pass

        # 3. If still not found, we might need to convert.
        # (Conversion logic omitted for MVP, assumed handled by pipeline or preemptive gen)
        
        raise FileNotFoundError(f"Could not find output for {kind}")

    def get_latest_output(self, beat_name: str) -> Dict:
        # Prefer state.json
        state = self.state_manager.get_state(beat_name)
        
        # 1. Try finding Stage 7 Final output (WAV or MP3)
        if state.get("latest_mp3") and Path(state["latest_mp3"]).exists():
             return {
                "beat_name": beat_name,
                "mp3_path": state["latest_mp3"],
                "wav_path": state.get("latest_wav", ""),
                "state": state
            }
        
        if state.get("latest_wav") and Path(state["latest_wav"]).exists():
             return {
                "beat_name": beat_name,
                # If only WAV exists, we can return it as "mp3_path" field if caller expects some audio path,
                # OR we return wav_path.
                # However, frontend usually asks for result.mp3_path or result.wav_path.
                # Let's populate what we have.
                "mp3_path": "", 
                "wav_path": state["latest_wav"],
                "state": state
            }
            
        # 2. Global fallback to Stage 7
        beat_name = beat_name.strip()
        output_root = (self.outs_root / beat_name).resolve()
        final_dir = output_root / "7_final"
        
        if final_dir.exists():
            mp3s = list(final_dir.glob("*_final.mp3"))
            wavs = list(final_dir.glob("*_final.wav"))
            
            if mp3s:
                latest_mp3 = max(mp3s, key=lambda p: p.stat().st_mtime)
                latest_wav = latest_mp3.with_suffix(".wav") # Assumption
                return {
                    "beat_name": beat_name,
                    "mp3_path": str(latest_mp3.resolve()),
                    "wav_path": str(latest_wav.resolve()) if latest_wav.exists() else "",
                    "final_dir": str(final_dir.resolve()),
                }
            elif wavs:
                latest_wav = max(wavs, key=lambda p: p.stat().st_mtime)
                return {
                    "beat_name": beat_name,
                    "mp3_path": "",
                    "wav_path": str(latest_wav.resolve()),
                    "final_dir": str(final_dir.resolve()),
                }

        # 3. Fallback to Stage 6 Preview
        # If no Stage 7 output, check Stage 6 preview
        s6_dir = output_root / "6_editor"
        if s6_dir.exists():
            previews = list(s6_dir.glob("preview_*.wav"))
            if previews:
                latest_preview = max(previews, key=lambda p: p.stat().st_mtime)
                # We return this as 'wav_path' effectively.
                # Frontend might prefer mp3 path, but we only have wav.
                return {
                    "beat_name": beat_name,
                    "mp3_path": "", # No MP3
                    "wav_path": str(latest_preview.resolve()),
                    "is_preview": True
                }

        raise FileNotFoundError(f"No audio output found for {beat_name} (checked s7 final and s6 preview)")
    
    def get_sample_path(self, beat_name: str, filename: str) -> Path:
        """Serves a specific sample from the 1_preprocess directory."""
        state = self.state_manager.get_state(beat_name)
        s1_dir = state.get("latest_s1_dir")
        
        if not s1_dir or not os.path.exists(s1_dir):
                raise FileNotFoundError("Preprocess directory not found")
        
        target_path = Path(s1_dir) / filename
        if not target_path.exists():
            target_path = Path(s1_dir) / "samples" / filename
        
        # If not found, try appending common extensions
        if not target_path.exists():
            for ext in [".wav", ".mp3", ".m4a", ".webm", ".flac"]:
                candidate = target_path.with_name(f"{filename}{ext}")
                if candidate.exists():
                    target_path = candidate
                    break
                candidate_sub = (Path(s1_dir) / "samples" / f"{filename}{ext}")
                if candidate_sub.exists():
                    target_path = candidate_sub
                    break
                    
        if not target_path.exists():
             raise FileNotFoundError("Sample file not found")
             
        return target_path
