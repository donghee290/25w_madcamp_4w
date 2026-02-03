from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import random

from .pools_io import extract_sample_ids_for_role


@dataclass
class SampleSelectorConfig:
    seed: int = 42
    mode: str = "round_robin"  # round_robin | fixed | random
    fixed_per_role: bool = True


class SampleSelector:
    def __init__(self, pools: Dict, cfg: SampleSelectorConfig):
        self.pools = pools
        self.cfg = cfg
        self.rng = random.Random(int(cfg.seed))
        self._rr_idx: Dict[str, int] = {}
        self._fixed: Dict[str, str] = {}

    def pick(self, role: str) -> str:
        role_u = role.upper()
        ids: List[str] = extract_sample_ids_for_role(self.pools, role_u)
        if not ids:
            return f"__MISSING__{role_u}"

        if self.cfg.mode == "fixed" or self.cfg.fixed_per_role:
            if role_u not in self._fixed:
                self._fixed[role_u] = ids[0]
            return self._fixed[role_u]

        if self.cfg.mode == "random":
            return self.rng.choice(ids)

        # round robin
        i = self._rr_idx.get(role_u, 0)
        sid = ids[i % len(ids)]
        self._rr_idx[role_u] = i + 1
        return sid

    def get_filepath(self, sample_id: str) -> Optional[str]:
        # DEBUG: Print structure for first call or specific ID
        debug = (sample_id == "drums")
        
        for pool_key, pool_data in self.pools.items():
             if isinstance(pool_data, list):
                 if debug: print(f"[DEBUG] Checking pool list {pool_key} (len={len(pool_data)})...")
                 for s in pool_data:
                     if isinstance(s, dict):
                         sid = str(s.get("sample_id"))
                         if debug: print(f"[DEBUG]   Compare '{sid}' vs '{sample_id}'")
                         if sid == str(sample_id):
                             fp = s.get("filepath")
                             if debug: print(f"[DEBUG]   MATCH! filepath={fp}")
                             return fp
             elif isinstance(pool_data, dict):
                 if debug: print(f"[DEBUG] Checking pool dict {pool_key}...")
                 samples = pool_data.get("samples", [])
                 if isinstance(samples, list):
                     for s in samples:
                         if isinstance(s, dict):
                             sid = str(s.get("sample_id"))
                             if sid == str(sample_id):
                                 return s.get("filepath")
        if debug: print(f"[DEBUG] Failed to find filepath for {sample_id}")
        return None