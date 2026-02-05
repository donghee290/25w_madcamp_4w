from __future__ import annotations
from typing import Dict, Any, List

# op 예시:
# {"op":"move_step","index":12,"delta":+1}
# {"op":"set_vel","index":5,"vel":0.8}

def apply_ops(events: List[Dict[str, Any]], ops: List[Dict[str, Any]], steps_per_bar: int = 16) -> List[Dict[str, Any]]:
    out = [dict(e) for e in events]

    for o in ops:
        op = str(o.get("op"))
        idx = int(o.get("index"))
        if idx < 0 or idx >= len(out):
            continue

        ev = out[idx]

        if op == "move_step":
            delta = int(o.get("delta", 0))
            bar = int(ev["bar"])
            step = int(ev["step"])
            new_step = step + delta
            # wrap bar/step
            while new_step < 0:
                bar -= 1
                new_step += steps_per_bar
            while new_step >= steps_per_bar:
                bar += 1
                new_step -= steps_per_bar
            if bar < 0:
                bar = 0
                new_step = 0
            ev["bar"] = bar
            ev["step"] = new_step

        elif op == "set_vel":
            vel = float(o.get("vel", ev.get("vel", 0.7)))
            ev["vel"] = max(0.0, min(1.0, vel))

        elif op == "set_micro":
            micro = float(o.get("micro_offset_ms", ev.get("micro_offset_ms", 0.0)))
            ev["micro_offset_ms"] = micro

        elif op == "delete":
            ev["_deleted"] = True

    out = [e for e in out if not e.get("_deleted")]
    out.sort(key=lambda e: (int(e["bar"]), int(e["step"])))
    return out