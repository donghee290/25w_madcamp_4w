from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
import os
import json
import hashlib

import numpy as np


def _softmax(x: np.ndarray, t: float = 1.0) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    t = max(float(t), 1e-8)
    z = x / t
    z = z - np.max(z)
    e = np.exp(z)
    return e / (np.sum(e) + 1e-12)


def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        out = []
        for s in x:
            s2 = str(s).strip()
            if s2:
                out.append(s2)
        return out
    s = str(x).strip()
    return [s] if s else []


def _stable_hash(obj: Any) -> str:
    b = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(b).hexdigest()[:16]


def _load_yaml(path: str) -> Dict[str, Any]:
    import yaml  # type: ignore
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _l2norm_np(v: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, ord=2, axis=-1, keepdims=True)
    return v / (n + eps)


class ClapScoreProbs:
    """
    fuse/fuse.py가 기대하는 형태:
      p_clap.values.get(role, 0.0)
    """
    def __init__(self, values: Dict[str, float]):
        self.values: Dict[str, float] = values


class ClapScoringConfig:
    """
    build_assigner_config에서 어떤 키워드가 들어와도 죽지 않도록 **kwargs 전부 수용.
    """

    def __init__(self, **kwargs):
        self.extra: Dict[str, Any] = dict(kwargs)

        # prompts
        self.prompts_yaml_path: Optional[str] = kwargs.get("prompts_yaml_path")
        self.prompts: Optional[Dict[str, Any]] = kwargs.get("prompts")

        # 온도 alias
        self.tau_clap: Optional[float] = kwargs.get("tau_clap")
        self.tau: Optional[float] = kwargs.get("tau")
        self.temperature: Optional[float] = kwargs.get("temperature")
        self.role_softmax_temperature: Optional[float] = kwargs.get("role_softmax_temperature")

        # 캐시 토글
        self.cache_text_embeddings: Optional[bool] = kwargs.get("cache_text_embeddings")

        # (받기만 하고 현재는 사용 안 함)
        self.ensemble_topk: Optional[int] = kwargs.get("ensemble_topk")

        # 내부 표준
        self.role_softmax_temp: float = float(kwargs.get("role_softmax_temp", 0.12))
        self.ensemble_method: str = str(kwargs.get("ensemble_method", "logsumexp"))
        self.prompt_temp: float = float(kwargs.get("prompt_temp", 0.07))
        self.w_general: float = float(kwargs.get("w_general", 1.0))
        self.w_specific: float = float(kwargs.get("w_specific", 1.0))

        # cache
        self.cache_dir: Optional[str] = kwargs.get("cache_dir")
        self.cache_version: str = str(kwargs.get("cache_version", "v6"))

        # alias -> role_softmax_temp
        cand = None
        if self.tau_clap is not None:
            cand = self.tau_clap
        elif self.role_softmax_temperature is not None:
            cand = self.role_softmax_temperature
        elif self.temperature is not None:
            cand = self.temperature
        elif self.tau is not None:
            cand = self.tau

        if cand is not None:
            self.role_softmax_temp = float(max(float(cand), 1e-6))

        # cache_text_embeddings가 False면 cache_dir 무시
        if self.cache_text_embeddings is False:
            self.cache_dir = None


class ClapScorer:
    """
    반환을 파이프라인 기대값에 맞춤:
      score(...) -> (sim_role: Dict[str, float], p_clap: ClapScoreProbs)

    - sim_role: 역할별 "유사도/로그릿" 딕셔너리 (role_assigner가 sim_role[r]로 접근)
    - p_clap: softmax 확률 딕셔너리 래퍼 (fusion이 p_clap.values.get(...)로 접근)
    """

    def __init__(self, backend, cfg: ClapScoringConfig):
        self.backend = backend
        self.cfg = cfg

        self.prompts: Dict[str, Any] = self._load_prompts(cfg)
        self.roles: List[str] = self._extract_roles(self.prompts)

        self.text_embeds: Dict[str, Dict[str, Optional[np.ndarray]]] = {}
        self.last_meta: Dict[str, Any] = {}

        self._prepare_text_embeddings()

    def _load_prompts(self, cfg: ClapScoringConfig) -> Dict[str, Any]:
        if cfg.prompts is not None:
            return cfg.prompts
        if cfg.prompts_yaml_path:
            return _load_yaml(cfg.prompts_yaml_path)
        raise ValueError("ClapScoringConfig requires prompts_yaml_path or prompts dict")

    @staticmethod
    def _extract_roles(prompts: Dict[str, Any]) -> List[str]:
        roles = prompts.get("roles")
        if not isinstance(roles, dict) or not roles:
            raise ValueError("prompts.yaml must contain top-level key: roles")
        return list(roles.keys())

    def _cache_path(self, role: str, group: str, texts: List[str]) -> Optional[str]:
        if not self.cfg.cache_dir:
            return None
        os.makedirs(self.cfg.cache_dir, exist_ok=True)
        key = {
            "ver": self.cfg.cache_version,
            "model": getattr(getattr(self.backend, "cfg", None), "model_id", "unknown"),
            "role": role,
            "group": group,
            "texts": texts,
        }
        h = _stable_hash(key)
        return os.path.join(self.cfg.cache_dir, f"clap_text_{role}_{group}_{h}.npy")

    def _embed_text_cached(self, role: str, group: str, texts: List[str]) -> np.ndarray:
        texts = _as_list(texts)
        if not texts:
            raise ValueError(f"empty texts for role={role}, group={group}")

        p = self._cache_path(role, group, texts)
        if p and os.path.exists(p):
            arr = np.load(p)
            arr = _l2norm_np(arr.astype(np.float32, copy=False))
            return arr

        emb = self.backend.embed_text(texts)  # (P,D)
        emb = np.asarray(emb, dtype=np.float32)

        # 방어: (P,T,D)면 T mean
        if emb.ndim == 3:
            emb = emb.mean(axis=1)
        if emb.ndim != 2:
            raise ValueError(f"embed_text must return 2D (P,D). got shape={emb.shape}")

        emb = _l2norm_np(emb)

        if p:
            np.save(p, emb)
        return emb

    def _prepare_text_embeddings(self) -> None:
        roles_block = self.prompts.get("roles", {})
        self.text_embeds = {}

        for role in self.roles:
            block = roles_block.get(role, {}) if isinstance(roles_block, dict) else {}
            general = _as_list(block.get("general"))
            specific = _as_list(block.get("specific"))

            gen_emb = self._embed_text_cached(role, "general", general) if general else None
            spc_emb = self._embed_text_cached(role, "specific", specific) if specific else None

            self.text_embeds[role] = {"general": gen_emb, "specific": spc_emb}

    def _ensemble_similarity(self, a: np.ndarray, text_embeds: np.ndarray) -> float:
        """
        a: (D,)
        text_embeds: (N, D)

        → N개 중 랜덤 K개만 사용해서 ensemble similarity 계산
        """

        # ---------- 랜덤 샘플링 파라미터 ----------
        K = getattr(self.cfg, "random_prompt_k", 32)  # 기본 32
        rng = np.random.default_rng()                 # seed 고정 원하면 여기서
        # -----------------------------------------

        # (N, D) 보장
        if text_embeds.ndim != 2:
            raise ValueError(f"text_embeds must be (N, D), got {text_embeds.shape}")

        N = text_embeds.shape[0]

        # 랜덤 서브샘플
        if N > K:
            idx = rng.choice(N, size=K, replace=False)
            text_embeds = text_embeds[idx]

        # cosine similarity (이미 L2 normalize 되어 있음)
        sims = np.dot(text_embeds, a)  # (K,)

        # ensemble 방식
        method = getattr(self.cfg, "ensemble_method", "mean")

        if method == "mean":
            return float(sims.mean())
        elif method == "max":
            return float(sims.max())
        elif method == "topk":
            k = min(getattr(self.cfg, "ensemble_topk", 3), sims.shape[0])
            return float(np.mean(np.partition(sims, -k)[-k:]))
        else:
            raise ValueError(f"Unknown ensemble_method: {method}")

    def score(self, y: np.ndarray, sr: int) -> Tuple[Dict[str, float], ClapScoreProbs]:
        a = self.backend.embed_audio(y, sr)
        a = np.asarray(a, dtype=np.float32).reshape(-1)

        # 역할별 "로그릿/유사도" 계산
        logits: List[float] = []
        for role in self.roles:
            gen = self.text_embeds[role].get("general")
            spc = self.text_embeds[role].get("specific")

            parts = []
            if gen is not None and gen.size > 0:
                parts.append(self.cfg.w_general * self._ensemble_similarity(a, gen))
            if spc is not None and spc.size > 0:
                parts.append(self.cfg.w_specific * self._ensemble_similarity(a, spc))

            logits.append(float(np.mean(parts)) if parts else -1e9)

        logits_np = np.asarray(logits, dtype=np.float32)

        # 1) role_assigner용: sim_role 딕셔너리
        sim_role = {self.roles[i]: float(logits_np[i]) for i in range(len(self.roles))}

        # 2) fusion용: softmax 확률 래퍼
        p = _softmax(logits_np, t=float(self.cfg.role_softmax_temp))
        probs = ClapScoreProbs({self.roles[i]: float(p[i]) for i in range(len(self.roles))})

        return sim_role, probs