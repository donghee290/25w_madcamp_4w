"""Pool balancing: ensure minimum samples per required role."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .scoring import DrumRole

logger = logging.getLogger("drumgenx")


def balance_pools(
    pools: Dict[DrumRole, List],
    all_scores: List[Dict[DrumRole, float]],
    all_items: List,
    pool_assignments: List[DrumRole],
    min_core: int = 1,
    min_accent: int = 1,
    min_motion: int = 1,
    max_per_role: Optional[int] = None,
) -> Tuple[Dict[DrumRole, List], List[DrumRole]]:
    """Balance role pools to meet minimum constraints."""
    assignments = list(pool_assignments)

    required_mins = {
        DrumRole.CORE: min_core,
        DrumRole.ACCENT: min_accent,
        DrumRole.MOTION: min_motion,
    }

    for req_role, min_count in required_mins.items():
        current_count = sum(1 for a in assignments if a == req_role)

        while current_count < min_count:
            best_idx = -1
            best_score = -1.0

            for i, (scores, current_role) in enumerate(zip(all_scores, assignments)):
                if current_role == req_role:
                    continue
                src_role = current_role
                src_count = sum(1 for a in assignments if a == src_role)
                if src_role in required_mins and src_count <= required_mins[src_role]:
                    continue

                candidate_score = scores.get(req_role, 0.0)
                if candidate_score > best_score:
                    best_score = candidate_score
                    best_idx = i

            if best_idx < 0:
                logger.warning(f"Cannot fill {req_role.value} pool to minimum {min_count}")
                break

            assignments[best_idx] = req_role
            current_count += 1
            logger.info(f"Promoted item {best_idx} to {req_role.value} (score={best_score:.3f})")

    if max_per_role is not None:
        for role in DrumRole:
            indices = [i for i, a in enumerate(assignments) if a == role]

            if len(indices) <= max_per_role:
                continue

            indices_with_scores = [(i, all_scores[i].get(role, 0.0)) for i in indices]
            indices_with_scores.sort(key=lambda x: x[1])

            excess = len(indices) - max_per_role
            to_move = indices_with_scores[:excess]

            for idx, _ in to_move:
                scores = all_scores[idx]
                sorted_roles = sorted(
                    [(r, s) for r, s in scores.items() if r != role],
                    key=lambda x: x[1],
                    reverse=True,
                )

                moved = False
                for alt_role, _ in sorted_roles:
                    alt_count = sum(1 for a in assignments if a == alt_role)
                    if max_per_role is not None and alt_count >= max_per_role:
                        continue
                    assignments[idx] = alt_role
                    moved = True
                    logger.info(f"Moved item {idx} from {role.value} to {alt_role.value}")
                    break

                if not moved:
                    assignments[idx] = DrumRole.TEXTURE
                    logger.info(f"Absorbed item {idx} into TEXTURE (catch-all)")

    balanced = {role: [] for role in DrumRole}
    for i, role in enumerate(assignments):
        balanced[role].append(all_items[i])

    for req_role, min_count in required_mins.items():
        actual = len(balanced[req_role])
        if actual < min_count:
            logger.warning(f"CONSTRAINT VIOLATION: {req_role.value} has {actual} < {min_count}")

    return balanced, assignments
