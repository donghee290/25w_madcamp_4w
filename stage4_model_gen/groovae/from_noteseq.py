# model_gen/groovae/from_noteseq.py
from __future__ import annotations

from typing import Dict, List
from stage4_model_gen.groovae.mapping import PITCH_TO_ROLE


def noteseq_to_events(
    ns,
    grid_json: Dict,
    sample_map: Dict[str, List[str]],
) -> List[Dict]:

    Tstep = grid_json["tstep"]
    Tbar = grid_json["tbar"]

    rr_idx = {k: 0 for k in sample_map}

    events = []

    for note in ns.notes:
        role = PITCH_TO_ROLE.get(note.pitch)
        if not role:
            continue

        bar = int(note.start_time // Tbar)
        step = int(round((note.start_time - bar * Tbar) / Tstep))

        vel = max(0.0, min(1.0, (note.velocity - 1) / 126))

        pool = sample_map.get(role, [])
        if not pool:
            continue

        sample_info = pool[rr_idx[role] % len(pool)]
        rr_idx[role] += 1
        
        # sample_info might be a dict (from role_pools) or just an ID string depending on usage.
        # Based on run_model_groovae, it's passing the raw pool dict list, so it's a dict.
        if isinstance(sample_info, dict):
            sid = str(sample_info.get("sample_id", "unknown"))
            fpath = str(sample_info.get("filepath", ""))
        else:
            sid = str(sample_info)
            fpath = ""

        events.append({
            "bar": bar,
            "step": step,
            "role": role,
            "sample_id": sid,
            "filepath": fpath,
            "vel": vel,
            "dur_steps": 1,
            "micro_offset_ms": (note.start_time - (bar * Tbar + step * Tstep)) * 1000.0,
            "source": "groovae",
        })

    return events