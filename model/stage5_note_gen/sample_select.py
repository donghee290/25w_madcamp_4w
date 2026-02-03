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