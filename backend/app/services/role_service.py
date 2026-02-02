from pathlib import Path
import yaml
from flask import current_app

# stage2 모듈 임포트 (sys.path에 프로젝트 루트가 잡혀있어야 함)
from stage2_role_assignment.role_assigner import RoleAssigner, RoleAssignerConfig
from stage2_role_assignment.dsp.audio_io import AudioLoadConfig
from stage2_role_assignment.dsp.features import DSPConfig
from stage2_role_assignment.dsp.rule_scoring import RuleScoringConfig, RuleWeights, TexturePenaltyConfig
from stage2_role_assignment.clap.backend import ClapBackendConfig
from stage2_role_assignment.clap.scoring import ClapScoringConfig
from stage2_role_assignment.fusion.fuse import FusionConfig

from stage2_role_assignment.pool.build_pools import build_pools, PoolConfig

class RoleService:
    _instance = None

    def __init__(self):
        self._assigner = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RoleService()
        return cls._instance

    def _load_assigner(self):
        if self._assigner is not None:
            return

        stage2_dir = current_app.config['STAGE2_DIR']
        config_path = stage2_dir / "configs" / "role_assignment.yaml"
        
        print(f"[RoleService] Loading config from {config_path}")
        with open(config_path, 'r') as f:
            cfg_dict = yaml.safe_load(f)
        
        # --- 수동 Config 조립 ---
        
        # 1. Audio
        audio_cfg = AudioLoadConfig(**cfg_dict['audio'])
        
        # 2. DSP (Tuple 변환)
        dsp_data = cfg_dict['dsp'].copy()
        
        # tau_rule 키가 dsp 섹션에 있으면 추출 (DSPConfig에는 없고 RuleScoringConfig에 필요)
        tau_rule_val = dsp_data.pop('tau_rule', 0.95)
        
        if 'band_edges_hz' in dsp_data:
            dsp_data['band_edges_hz'] = {
                k: tuple(v) if isinstance(v, list) else v
                for k, v in dsp_data['band_edges_hz'].items()
            }
        dsp_cfg = DSPConfig(**dsp_data)
        
        # 3. Rule Scoring
        rs_data = cfg_dict['rule_scoring']
        w_data = rs_data['weights']
        weights = RuleWeights(
            core=w_data['core'],
            accent=w_data['accent'],
            motion=w_data['motion'],
            fill=w_data['fill'],
            texture=w_data['texture']
        )
        tp_data = rs_data.get('texture_penalty', {})
        tp_cfg = TexturePenaltyConfig(**tp_data) if tp_data else None
        
        rs_cfg = RuleScoringConfig(
            weights=weights,
            tau_rule=tau_rule_val, # 추출한 값 사용
            texture_penalty=tp_cfg
        )
        
        # 5. CLAP (YAML 'clap' -> Backend / Scoring)
        clap_data = cfg_dict['clap']
        # 필요한 필드만 추출하여 생성
        # 'backend' 키는 Config 클래스에 없으므로 제거
        c_backend_cfg = ClapBackendConfig(
            model_id=clap_data.get('model_id', 'laion/clap-htsat-unfused'),
            device=clap_data.get('device', 'auto')
        )
        
        prompts_path = stage2_dir / "prompts" / "prompts.yaml"
        c_scoring_cfg = ClapScoringConfig(
            audio_pooling=clap_data.get('audio_pooling', 'mean'),
            tau_clap=clap_data.get('tau_clap', 0.07),
            cache_text_embeddings=clap_data.get('cache_text_embeddings', True),
            cache_dir=clap_data.get('cache_dir', '.cache/clap_text'),
            prompts_yaml_path=str(prompts_path),
            ensemble_method="mean"
        )

        # 5. Fusion
        fusion_cfg = FusionConfig(**cfg_dict['fusion'])

        # 6. Pool
        pool_data = cfg_dict['pool']
        self._pool_config = PoolConfig(
            required_roles=pool_data['required_roles'],
            max_sizes=pool_data['max_sizes'],
            promote_when_missing_enabled=pool_data.get('promote_when_missing', {}).get('enabled', True),
            forbid_core_if_decay_long_threshold=pool_data.get('promote_when_missing', {}).get('forbid_core_if', {}).get('decay_long_threshold', 0.75),
            forbid_core_if_flatness_threshold=pool_data.get('promote_when_missing', {}).get('forbid_core_if', {}).get('flatness_threshold', 0.25),
            forbid_motion_if_high_ratio_threshold=pool_data.get('promote_when_missing', {}).get('forbid_motion_if', {}).get('high_ratio_threshold', 0.25),
            
            rebalance_when_excess_enabled=pool_data.get('rebalance_when_excess', {}).get('enabled', True),
            min_margin_keep=pool_data.get('rebalance_when_excess', {}).get('min_margin_keep', 0.08),
            try_third_best_if_target_excess=pool_data.get('rebalance_when_excess', {}).get('try_third_best_if_target_excess', True)
        )

        # Final Config
        cfg = RoleAssignerConfig(
            audio=audio_cfg,
            dsp=dsp_cfg,
            rule_scoring=rs_cfg,
            clap_backend=c_backend_cfg,
            clap_scoring=c_scoring_cfg,
            fusion=fusion_cfg
        )
        
        # 모델 로드 (시간 소요)
        print("[RoleService] Initializing RoleAssigner (loading CLAP model)...")
        self._assigner = RoleAssigner(cfg)
        print("[RoleService] RoleAssigner ready.")

    def process_files(self, file_paths):
        """
        List[Path or str] -> RolePools
        """
        self._load_assigner()
        
        results = []
        for fp in file_paths:
            path_obj = Path(fp)
            sample_id = path_obj.stem
            
            # assign_file 호출
            res = self._assigner.assign_file(str(fp), sample_id=sample_id)
            results.append(res)
        
        # 풀 빌드
        pools = build_pools(results, self._pool_config)
        return pools

# 편의를 위한 싱글톤 접근 함수
def get_role_service():
    return RoleService.get_instance()
