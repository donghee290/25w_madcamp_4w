from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Any

import numpy as np
import torch
import resampy
from transformers import ClapModel, ClapProcessor


@dataclass
class ClapBackendConfig:
    model_id: str = "laion/clap-htsat-unfused"
    device: str = "auto"  # auto | cpu | cuda
    audio_pooling: str = "mean"  # mean | max (현재는 mean만 사용)


def _ensure_tensor(x: Any) -> torch.Tensor:
    """
    transformers output에서 torch.Tensor를 최대한 안정적으로 추출.
    - Tensor면 그대로
    - ModelOutput/dict면 흔한 키 우선 탐색
    - tuple/list면 첫 Tensor 반환
    """
    if isinstance(x, torch.Tensor):
        return x

    # ModelOutput / dict-like
    if hasattr(x, "keys") and callable(getattr(x, "keys")):
        # 가장 유력한 키들
        for k in ["text_embeds", "audio_embeds", "embeds", "pooler_output", "last_hidden_state"]:
            if k in x and isinstance(x[k], torch.Tensor):
                return x[k]
        # fallback: first tensor
        for v in x.values():
            if isinstance(v, torch.Tensor):
                return v

    # tuple/list
    if isinstance(x, (tuple, list)):
        for v in x:
            if isinstance(v, torch.Tensor):
                return v

    raise TypeError(f"CLAP output is not torch.Tensor-like. type={type(x)}")


class ClapBackend:
    """
    Transformers 기반 CLAP 백엔드.

    핵심 안정화 포인트:
    1) 오디오 입력은 모델 feature extractor가 요구하는 SR(대부분 48000)로 강제 리샘플
    2) processor(audio=...) / processor(audios=...) 버전 호환
    3) forward()는 텍스트 input_ids가 없으면 터질 수 있으니 사용 금지
       - 텍스트: get_text_features()
       - 오디오: get_audio_features()
    4) 임베딩 shape가 (N,T,D)처럼 3D로 나오면 T축 mean pooling으로 (N,D)로 정리
    5) 항상 L2 normalize 후 numpy float32 반환
    """

    def __init__(self, cfg: ClapBackendConfig):
        self.cfg = cfg
        self.device = self._pick_device(cfg.device)

        self.processor = ClapProcessor.from_pretrained(cfg.model_id)
        self.model = ClapModel.from_pretrained(cfg.model_id)
        self.model.to(self.device)
        self.model.eval()

        self.embed_dim: Optional[int] = None

        # CLAP feature extractor가 학습에 사용한 sampling rate (대부분 48000)
        fe = getattr(self.processor, "feature_extractor", None)
        self.target_sr = int(getattr(fe, "sampling_rate", 48000))

    @staticmethod
    def _pick_device(device: str) -> torch.device:
        if device == "cpu":
            return torch.device("cpu")
        if device == "cuda":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _l2_normalize(self, x: torch.Tensor, eps: float = 1e-12) -> torch.Tensor:
        x = _ensure_tensor(x)
        return x / (x.norm(p=2, dim=-1, keepdim=True) + eps)

    @staticmethod
    def _pool_if_3d(x: torch.Tensor) -> torch.Tensor:
        """
        (N,T,D) -> (N,D) mean pooling
        (1,T,D) -> (1,D)
        """
        if isinstance(x, torch.Tensor) and x.ndim == 3:
            return x.mean(dim=1)
        return x

    @torch.no_grad()
    def embed_text(self, texts: List[str]) -> np.ndarray:
        """
        texts -> (N, D) numpy float32 (L2 normalized)
        """
        if not texts:
            raise ValueError("embed_text: texts is empty")

        inputs = self.processor(text=texts, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # 텍스트 전용 API 사용 (forward() 금지)
        out = self.model.get_text_features(**inputs)
        text_features = _ensure_tensor(out)
        text_features = self._pool_if_3d(text_features)
        text_features = self._l2_normalize(text_features)

        if self.embed_dim is None:
            self.embed_dim = int(text_features.shape[-1])

        return text_features.detach().cpu().numpy().astype(np.float32, copy=False)

    @torch.no_grad()
    def embed_audio(self, y: np.ndarray, sr: int) -> np.ndarray:
        """
        audio -> (D,) numpy float32 (L2 normalized)
        - CLAP 요구 SR로 강제 리샘플
        - processor 키워드 호환(audio / audios)
        - 오디오 전용 API(get_audio_features) 사용
        """
        if y is None:
            raise ValueError("embed_audio: y is None")
        y = np.asarray(y, dtype=np.float32)
        if y.size == 0:
            raise ValueError("embed_audio: empty audio")

        # mono로 정리
        if y.ndim > 1:
            y = np.mean(y, axis=0).astype(np.float32, copy=False)

        # 48k 강제 리샘플
        if int(sr) != int(self.target_sr):
            y = resampy.resample(y, int(sr), int(self.target_sr)).astype(np.float32, copy=False)
            sr = int(self.target_sr)

        # processor 버전 호환
        try:
            inputs = self.processor(
                audio=y,
                sampling_rate=int(sr),
                return_tensors="pt",
                padding=True,
            )
        except (TypeError, ValueError):
            inputs = self.processor(
                audios=y,
                sampling_rate=int(sr),
                return_tensors="pt",
                padding=True,
            )

        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # 오디오 전용 API 사용 (forward() 금지)
        out = self.model.get_audio_features(**inputs)
        audio_features = _ensure_tensor(out)
        audio_features = self._pool_if_3d(audio_features)

        # 혹시 batch가 여러 개면 첫 개만
        if audio_features.ndim == 2 and audio_features.shape[0] > 1:
            audio_features = audio_features[:1]

        audio_features = self._l2_normalize(audio_features)

        if self.embed_dim is None:
            self.embed_dim = int(audio_features.shape[-1])

        # (1,D) -> (D,)
        return audio_features[0].detach().cpu().numpy().astype(np.float32, copy=False)

    @staticmethod
    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        """
        a, b: (D,) (L2 normalized라고 가정)
        """
        a = np.asarray(a, dtype=np.float32).reshape(-1)
        b = np.asarray(b, dtype=np.float32).reshape(-1)
        return float(np.dot(a, b))