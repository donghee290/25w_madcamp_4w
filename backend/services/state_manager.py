import json
import time
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, outs_root: Path):
        self.outs_root = outs_root

    def _get_project_dir(self, beat_name: str) -> Path:
        return self.outs_root / beat_name

    def _get_state_path(self, beat_name: str) -> Path:
        return self._get_project_dir(beat_name) / "state.json"

    def get_state(self, beat_name: str) -> Dict[str, Any]:
        """Reads state.json for the project."""
        p = self._get_state_path(beat_name)
        if not p.exists():
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read state.json for {beat_name}: {e}")
            return {}

    def update_state(self, beat_name: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates specific keys in state.json and saves it."""
        current = self.get_state(beat_name)
        current.update(updates)
        current["updated_at"] = time.time()

        p = self._get_state_path(beat_name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        return current
    def rename_project(self, old_name: str, new_name: str) -> Path:
        """Renames the project directory and returns the new path."""
        old_dir = self._get_project_dir(old_name)
        new_dir = self._get_project_dir(new_name)
        
        if not old_dir.exists():
            raise FileNotFoundError(f"Source project folder not found: {old_dir}")
            
        if new_dir.exists():
            # If target exists, maybe append a suffix or just error?
            # User wants beatname_timestamp, so we assume uniqueness if we append timestamp.
            # For now, let's just move if it doesn't exist.
            pass
            
        import shutil
        shutil.move(str(old_dir), str(new_dir))
        
        # After move, we might need to update paths INSIDE state.json if they are absolute.
        state = self.get_state(new_name)
        updated = False
        old_dir_str = str(old_dir.resolve())
        new_dir_str = str(new_dir.resolve())
        
        def update_paths(d):
            nonlocal updated
            for k, v in d.items():
                if isinstance(v, str) and old_dir_str in v:
                    d[k] = v.replace(old_dir_str, new_dir_str)
                    updated = True
                elif isinstance(v, dict):
                    update_paths(v)
        
        update_paths(state)
        if updated:
            self.update_state(new_name, state)
            
        return new_dir
