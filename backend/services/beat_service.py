from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from flask import current_app

from stage3_beat_grid.grid import GridConfig, build_grid
from stage3_beat_grid.patterns.skeleton import SkeletonConfig, build_skeleton_events
from stage3_beat_grid.test_audio_render.render import render_events


class BeatService:
    def generate_beat(
        self,
        pools_data: Any,
        bpm: float = 120.0,
        bars: int = 4,
        seed: int = 42,
        motion_mode: str = "B",
        motion_keep: int = 6,
        fill_prob: float = 0.25,
        texture_enabled: bool = True,
        output_filename: str = "output.wav",
        sample_root: Path | None = None,
    ) -> Dict[str, Any]:
        """
        Generate grid + skeleton events and render audio.
        pools_data: RolePools object or dict
        """
        grid_cfg = GridConfig(bpm=bpm, num_bars=bars)
        grid = build_grid(grid_cfg)

        # Normalize pools to *_POOL keys and dict items
        if hasattr(pools_data, "as_dict"):
            raw = pools_data.as_dict()
        else:
            raw = pools_data

        pools_dict: Dict[str, Any] = {}
        for k, v in raw.items():
            key = k if str(k).endswith("_POOL") else f"{k}_POOL"
            if isinstance(v, list):
                converted = []
                for item in v:
                    if isinstance(item, dict):
                        converted.append(item)
                    else:
                        converted.append(
                            {
                                "sample_id": getattr(item, "sample_id", ""),
                                "filepath": getattr(item, "filepath", ""),
                                "role": str(getattr(item, "role", "")),
                                "confidence": getattr(
                                    getattr(item, "scores", None), "confidence", 0.0
                                )
                                if hasattr(item, "scores")
                                else 0.0,
                                "features": {
                                    "energy": getattr(
                                        getattr(item, "features", None), "energy", None
                                    ),
                                    "decay_time": getattr(
                                        getattr(item, "features", None), "decay_time", None
                                    ),
                                }
                                if hasattr(item, "features") and item.features
                                else {},
                            }
                        )
                pools_dict[key] = converted
            else:
                pools_dict[key] = v

        skel_cfg = SkeletonConfig(
            seed=int(seed),
            steps_per_bar=16,
            num_bars=int(bars),
            motion_mode=str(motion_mode),
            motion_keep_per_bar=int(motion_keep),
            fill_prob=float(fill_prob),
            texture_enabled=bool(texture_enabled),
        )
        events, chosen = build_skeleton_events(
            pools_dict, skel_cfg, tstep=grid.tstep
        )

        # Resolve output path
        out_root = Path(current_app.config["OUTPUT_FOLDER"])
        out_path = out_root / output_filename
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Map sample_id -> filepath for rendering
        id_to_path: Dict[str, str] = {}
        for samples in pools_dict.values():
            if isinstance(samples, list):
                for s in samples:
                    if isinstance(s, dict):
                        s_id = s.get("sample_id")
                        s_path = s.get("filepath")
                    else:
                        s_id = getattr(s, "sample_id", None)
                        s_path = getattr(s, "filepath", None)
                    if s_id and s_path:
                        id_to_path[str(s_id)] = str(s_path)

        events_dict_list = []
        for e in events:
            ev_dict = {
                "bar": e.bar,
                "step": e.step,
                "role": e.role,
                "sample_id": e.sample_id,
                "vel": e.vel,
                "dur_steps": e.dur_steps,
                "micro_offset_ms": e.micro_offset_ms,
            }
            if e.sample_id in id_to_path:
                ev_dict["filepath"] = id_to_path[e.sample_id]
            events_dict_list.append(ev_dict)

        grid_json = {
            "bpm": grid.cfg.bpm,
            "meter": f"{grid.cfg.meter_numer}/{grid.cfg.meter_denom}",
            "steps_per_bar": grid.cfg.steps_per_bar,
            "num_bars": grid.cfg.num_bars,
            "tbeat": grid.tbeat,
            "tbar": grid.tbar,
            "tstep": grid.tstep,
            "bar_start": grid.bar_start,
            "t_step": grid.t_step,
        }

        render_events(
            grid_json=grid_json,
            events=events_dict_list,
            sample_root=sample_root
            if sample_root is not None
            else Path(current_app.config["UPLOAD_FOLDER"]),
            out_wav=out_path,
            target_sr=44100,
            master_gain=1.0,
        )

        return {
            "grid": grid_json,
            "events": events_dict_list,
            "chosen_samples": chosen,
            "audio_url": f"/output/{output_filename}",
            "audio_path": str(out_path),
        }


def get_beat_service() -> BeatService:
    return BeatService()
