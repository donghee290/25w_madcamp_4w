from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Dict, Any

import yaml
import random
import re
from tqdm import tqdm

from stage2_role_assignment.role_assigner import (
    RoleAssigner,
    RoleAssignerConfig,
)
from stage2_role_assignment.dsp.audio_io import AudioLoadConfig
from stage2_role_assignment.dsp.features import DSPConfig
from stage2_role_assignment.dsp.rule_scoring import (
    RuleScoringConfig,
    RuleWeights,
    TexturePenaltyConfig,
)
from stage2_role_assignment.clap.backend import ClapBackendConfig
from stage2_role_assignment.clap.scoring import ClapScoringConfig
from stage2_role_assignment.fusion.fuse import FusionConfig
from stage2_role_assignment.fusion.guards import GuardsConfig, TextureSuppressConfig, SustainedNoiseSuppressConfig, MotionMinConditionConfig, FillConservativeConfig, LowConfTextureExtraSuppressConfig
from stage2_role_assignment.pool.build_pools import PoolConfig, build_pools, pools_to_json_dict


AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", type=str, required=True)
    p.add_argument("--out_dir", type=str, required=True)

    p.add_argument("--config", type=str, default="role_assignment/configs/role_assignment.yaml")
    p.add_argument("--prompts", type=str, default="role_assignment/prompts/prompts.yaml")

    p.add_argument("--limit", type=int, default=0, help="0이면 전체, 아니면 앞에서 N개만")
    return p.parse_args()


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_assigner_config(cfg_dict: Dict[str, Any], prompts_path: str) -> tuple[RoleAssignerConfig, PoolConfig, Dict[str, Any]]:
    """
    role_assignment.yaml을 파이썬 dataclass config로 변환
    """
    # --- audio ---
    audio_cfg = AudioLoadConfig(
        target_sr=int(cfg_dict["audio"]["target_sr"]),
        mono=bool(cfg_dict["audio"]["mono"]),
        max_duration_sec=float(cfg_dict["audio"]["max_duration_sec"]),
        trim_silence=bool(cfg_dict["audio"]["trim_silence"]),
        trim_top_db=int(cfg_dict["audio"]["trim_top_db"]),
        peak_normalize=bool(cfg_dict["audio"]["peak_normalize"]),
        peak_target=float(cfg_dict["audio"]["peak_target"]),
    )

    # --- dsp ---
    be = cfg_dict["dsp"]["band_edges_hz"]
    dsp_cfg = DSPConfig(
        frame_length=int(cfg_dict["dsp"]["frame_length"]),
        hop_length=int(cfg_dict["dsp"]["hop_length"]),
        band_edges_hz={
            "low": (float(be["low"][0]), float(be["low"][1])),
            "mid": (float(be["mid"][0]), float(be["mid"][1])),
            "high": (float(be["high"][0]), float(be["high"][1])),
        },
        attack_window_sec=float(cfg_dict["dsp"]["attack_window_sec"]),
        decay_window_sec=float(cfg_dict["dsp"]["decay_window_sec"]),
    )

    # --- rule scoring ---
    w = cfg_dict["rule_scoring"]["weights"]
    weights = RuleWeights(
        core=dict(w["core"]),
        accent=dict(w["accent"]),
        motion=dict(w["motion"]),
        fill=dict(w["fill"]),
        texture=dict(w["texture"]),
    )

    tp = cfg_dict["rule_scoring"]["texture_penalty"]
    tex_pen = TexturePenaltyConfig(
        enabled=bool(tp["enabled"]),
        transient_S_threshold=float(tp["transient_S_threshold"]),
        decay_short_threshold=float(tp["decay_short_threshold"]),
        penalty=float(tp["penalty"]),
        use_flatness_gate=bool(tp["use_flatness_gate"]),
        flatness_threshold=float(tp["flatness_threshold"]),
        flatness_penalty=float(tp["flatness_penalty"]),
    )

    rule_cfg = RuleScoringConfig(
        weights=weights,
        tau_rule=float(cfg_dict["dsp"]["tau_rule"]),
        texture_penalty=tex_pen,
    )

    # --- clap ---
    clap_backend_cfg = ClapBackendConfig(
        model_id=str(cfg_dict["clap"]["model_id"]),
        device="auto",
        audio_pooling=str(cfg_dict["clap"]["audio_pooling"]),
    )

    clap_scoring_cfg = ClapScoringConfig(
        prompts_yaml_path=prompts_path,
        tau_clap=float(cfg_dict["clap"]["tau_clap"]),
        cache_text_embeddings=bool(cfg_dict["clap"]["cache_text_embeddings"]),
        cache_dir=str(cfg_dict["clap"]["cache_dir"]),
        ensemble_method=str(cfg_dict["prompts_ensemble"]["method"]) if "prompts_ensemble" in cfg_dict else "mean",
        ensemble_topk=int(cfg_dict["prompts_ensemble"]["topk"]) if "prompts_ensemble" in cfg_dict else 3,
    )

    # --- guards + fusion ---
    guards_d = cfg_dict.get("guards", {})
    guards_cfg = GuardsConfig(
        enabled=bool(guards_d.get("enabled", True)),
        texture_suppress=TextureSuppressConfig(**guards_d.get("texture_suppress", {})),
        sustained_noise_suppress=SustainedNoiseSuppressConfig(**guards_d.get("sustained_noise_suppress", {})),
        motion_min_condition=MotionMinConditionConfig(**guards_d.get("motion_min_condition", {})),
        fill_conservative=FillConservativeConfig(**guards_d.get("fill_conservative", {})),
        low_conf_texture_extra_suppress=LowConfTextureExtraSuppressConfig(**guards_d.get("low_conf_texture_extra_suppress", {})),
    )

    fusion_cfg = FusionConfig(
        alpha=float(cfg_dict["fusion"]["alpha"]),
        role_bias=cfg_dict.get("prompts", {}).get("postprocess", {}).get("role_bias", None),
        confidence_margin_threshold=float(cfg_dict["fusion"]["confidence_margin_threshold"]),
        guards=guards_cfg,
    )

    assigner_cfg = RoleAssignerConfig(
        audio=audio_cfg,
        dsp=dsp_cfg,
        rule_scoring=rule_cfg,
        clap_backend=clap_backend_cfg,
        clap_scoring=clap_scoring_cfg,
        fusion=fusion_cfg,
    )

    # --- pool ---
    pool_d = cfg_dict["pool"]
    pool_cfg = PoolConfig(
        required_roles=list(pool_d["required_roles"]),
        max_sizes={k: int(v) for k, v in pool_d["max_sizes"].items()},
        promote_when_missing_enabled=bool(pool_d["promote_when_missing"]["enabled"]),
        forbid_core_if_decay_long_threshold=float(pool_d["promote_when_missing"]["forbid_core_if"]["decay_long_threshold"]),
        forbid_core_if_flatness_threshold=float(pool_d["promote_when_missing"]["forbid_core_if"]["flatness_threshold"]),
        forbid_motion_if_high_ratio_threshold=float(pool_d["promote_when_missing"]["forbid_motion_if"]["high_ratio_threshold"]),
        rebalance_when_excess_enabled=bool(pool_d["rebalance_when_excess"]["enabled"]),
        min_margin_keep=float(pool_d["rebalance_when_excess"]["min_margin_keep"]),
        try_third_best_if_target_excess=bool(pool_d["rebalance_when_excess"]["try_third_best_if_target_excess"]),
    )

    return assigner_cfg, pool_cfg, cfg_dict


def list_audio_files(input_dir: str) -> List[Path]:
    root = Path(input_dir)
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            files.append(p)
    return sorted(files)


def _k(x):
    return x.value if hasattr(x, "value") else str(x)

def sample_result_to_debug_dict(sr) -> Dict[str, Any]:
    return {
        "sample_id": sr.sample_id,
        "filepath": sr.filepath,
        "role": _k(sr.role),
        "confidence": float(sr.scores.confidence),

        "p_rule": {_k(k): float(v) for k, v in sr.scores.rule.values.items()},
        "p_clap": {_k(k): float(v) for k, v in sr.scores.clap.values.items()},
        "p_final": {_k(k): float(v) for k, v in sr.scores.final.values.items()},

        "rule_raw": {_k(k): float(v) for k, v in (sr.rule_raw_scores or {}).items()},
        "clap_sim": {_k(k): float(v) for k, v in (sr.clap_similarities or {}).items()},

        "features": {
            "energy": sr.features.energy,
            "rms": sr.features.rms,
            "sharpness": sr.features.sharpness,
            "attack_time": sr.features.attack_time,
            "decay_time": sr.features.decay_time,
            "low_ratio": sr.features.low_ratio,
            "mid_ratio": sr.features.mid_ratio,
            "high_ratio": sr.features.high_ratio,
            "spectral_flatness": sr.features.spectral_flatness,
            "zero_crossing_rate": sr.features.zero_crossing_rate,
        },
    }


def main():
    args = parse_args()

    input_dir = args.input_dir
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_yaml(args.config)

    # prompts_ensemble 키가 prompts.yaml에 있고 role_assignment.yaml에는 없을 수 있으니,
    # prompts.yaml의 ensemble을 읽어 cfg에 반영(있으면)
    prompts_yaml = load_yaml(args.prompts)
    if "ensemble" in prompts_yaml:
        cfg["prompts_ensemble"] = {
            "method": prompts_yaml["ensemble"].get("method", "mean"),
            "topk": prompts_yaml["ensemble"].get("topk", 3),
        }

    assigner_cfg, pool_cfg, _cfg_dict = build_assigner_config(cfg, prompts_path=args.prompts)

    assigner = RoleAssigner(assigner_cfg)

    files = list_audio_files(input_dir)
    
    # 2. Randomly select 10 files (shuffle first)
    random.shuffle(files)
    
    if args.limit and args.limit > 0:
        files = files[: args.limit]
    else:
        # Default behavior per user request: random 10
        files = files[:10]

    if not files:
        raise RuntimeError(f"No audio files found in: {input_dir}")

    results = []
    for f in tqdm(files, desc="Assign roles"):
        sr = assigner.assign_file(f)
        results.append(sr)

    pools = build_pools(results, pool_cfg)
    pools_json = pools_to_json_dict(pools)

    # Output filenames with numbering
    base_pools_name = cfg["output"]["pools_json"]
    base_debug_name = cfg["output"]["per_sample_json"]

    def get_next_filename(base_name: str, directory: Path) -> str:
        stem = Path(base_name).stem
        ext = Path(base_name).suffix
        # Pattern: name_{n}.ext
        pattern = re.compile(rf"^{re.escape(stem)}_(\d+){re.escape(ext)}$")
        
        max_idx = 0
        for f in directory.iterdir():
            if not f.is_file():
                continue
            m = pattern.match(f.name)
            if m:
                idx = int(m.group(1))
                if idx > max_idx:
                    max_idx = idx
            elif f.name == base_name: # Handle case where file has no number yet (treat as 0 or handle separately?)
                 pass # We want strictly numbered files from now on? Or next is _1

        # Always start from 1 if no numbered files found, or max + 1
        return f"{stem}_{max_idx + 1}{ext}"

    pools_name = get_next_filename(base_pools_name, out_dir)
    # Match numbering for debug file
    # We assume they should share the ID for better correlation
    # Extract the ID from pools_name
    
    # Simple way: just call get_next_filename for debug too?
    # Risk: if pools_name exists but debug doesn't... separate numbering.
    # Better: Extract the number we just generated.
    
    generated_suffix = pools_name.replace(Path(base_pools_name).stem, "").replace(Path(base_pools_name).suffix, "")
    # generated_suffix is like "_1"
    
    debug_name = Path(base_debug_name).stem + generated_suffix + Path(base_debug_name).suffix
    
    (out_dir / pools_name).write_text(json.dumps(pools_json, ensure_ascii=False, indent=2), encoding="utf-8")
    
    debug_list = [sample_result_to_debug_dict(x) for x in results]
    (out_dir / debug_name).write_text(json.dumps(debug_list, ensure_ascii=False, indent=2), encoding="utf-8")

    # 콘솔 요약
    counts = pools_json["counts"]
    print("[DONE] role assignment complete")
    print(" - out_dir:", str(out_dir))
    print(" - pools:", str(out_dir / pools_name))
    print(" - debug:", str(out_dir / debug_name))
    print(" - counts:", counts)


if __name__ == "__main__":
    main()