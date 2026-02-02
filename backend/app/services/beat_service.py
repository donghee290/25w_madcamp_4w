from pathlib import Path
from flask import current_app
import dataclasses

from stage3_beat_grid.grid import GridConfig, build_grid
from stage3_beat_grid.patterns.skeleton import SkeletonConfig, build_skeleton_events
from stage3_beat_grid.test_audio_render.render import render_events

class BeatService:
    def generate_beat(self, pools_data, bpm=120.0, bars=4, output_filename="output.wav"):
        """
        Generates a beat grid, skeleton patterns, and renders audio.
        
        Args:
            pools_data: RolePools object or dictionary from Stage 2
            bpm: Beats per minute
            bars: Number of bars
            output_filename: Name of the output wav file
            
        Returns:
            dict containing grid, events, and audio file path
        """
        # 1. Grid Configuration
        grid_cfg = GridConfig(bpm=bpm, num_bars=bars)
        grid = build_grid(grid_cfg)
        
        # 2. Skeleton Generation
        # RolePools.as_dict() returns {"CORE": [...], ...}
        # but build_skeleton_events expects {"CORE_POOL": [...], ...}
        if hasattr(pools_data, 'as_dict'):
            raw = pools_data.as_dict()
        else:
            raw = pools_data

        # Ensure keys have _POOL suffix (skeleton builder requires it)
        pools_dict = {}
        for k, v in raw.items():
            key = k if k.endswith("_POOL") else f"{k}_POOL"
            # Convert SampleResult objects to dicts if needed
            if isinstance(v, list):
                converted = []
                for item in v:
                    if isinstance(item, dict):
                        converted.append(item)
                    else:
                        converted.append({
                            "sample_id": getattr(item, "sample_id", ""),
                            "filepath": getattr(item, "filepath", ""),
                            "role": str(getattr(item, "role", "")),
                            "confidence": getattr(getattr(item, "scores", None), "confidence", 0.0) if hasattr(item, "scores") else 0.0,
                            "features": {
                                "energy": getattr(getattr(item, "features", None), "energy", None),
                                "decay_time": getattr(getattr(item, "features", None), "decay_time", None),
                            } if hasattr(item, "features") and item.features else {},
                        })
                pools_dict[key] = converted
            else:
                pools_dict[key] = v

        skel_cfg = SkeletonConfig(num_bars=bars, motion_mode="A")
        events, chosen_samples = build_skeleton_events(pools_dict, skel_cfg, tstep=grid.tstep)
        
        # 3. Prepare for Rendering
        out_path = current_app.config['OUTPUT_FOLDER'] / output_filename
        
        # Convert Event objects to dicts and inject filepath
        # Create a map of sample_id -> filepath from pools
        id_to_path = {}
        # pools_dict structure: {"CORE_POOL": [...], ...}
        # keys end with _POOL usually, but let's iterate all lists
        for key, samples in pools_dict.items():
            if isinstance(samples, list):
                for s in samples:
                    # s can be dict (from json) or SampleResult object (from memory)
                    if isinstance(s, dict):
                        s_id = s.get('sample_id')
                        s_path = s.get('filepath')
                    else:
                        s_id = getattr(s, 'sample_id', None)
                        s_path = getattr(s, 'filepath', None)
                    
                    if s_id and s_path:
                        id_to_path[s_id] = str(s_path)
            
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
            # Inject absolute filepath if available
            if e.sample_id in id_to_path:
                ev_dict['filepath'] = id_to_path[e.sample_id]
            
            events_dict_list.append(ev_dict)
        
        # Grid object to flat dict (render_events expects top-level keys)
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
        
        # 4. Render Audio
        # Assuming render_events handles mixing
        render_events(
            grid_json=grid_json,
            events=events_dict_list,
            sample_root=current_app.config['UPLOAD_FOLDER'], # Fallback root
            out_wav=out_path,
            target_sr=44100,
            master_gain=1.0 # Slightly louder
        )
        
        return {
            "grid": grid_json,
            "events": events_dict_list,
            "audio_url": f"/output/{output_filename}", # Assuming static file serving
            "audio_path": str(out_path)
        }

def get_beat_service():
    return BeatService()
