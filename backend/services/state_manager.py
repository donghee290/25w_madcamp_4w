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
