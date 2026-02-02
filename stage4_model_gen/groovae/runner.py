# model_gen/groovae/runner.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from note_seq.protobuf import music_pb2


@dataclass
class GrooVAEModelConfig:
    # Magenta MusicVAE config name (대표적으로 drum/groovae 계열)
    # 예: "groovae_2bar_humanize", "groovae_4bar", "drums_2bar_lokl" 등
    # 실제 설치된 magenta 버전에 따라 이름이 다를 수 있습니다.
    config_name: str = "groovae_2bar_humanize"

    # 체크포인트 디렉토리(필수)
    # 예: /home/dh/checkpoints/groovae_2bar_humanize
    checkpoint_dir: str = ""

    # 샘플링 파라미터 (필요시)
    temperature: float = 1.0

    # 입력 길이에 맞춰 생성 길이를 맞추고 싶으면,
    # num_steps를 직접 쓰기보다 "입력의 총 quantized step"을 기반으로 잘라내는 후처리를 권장합니다.
    # 여기서는 간단히 "생성 결과를 입력 길이에 맞춰 자르는" 옵션만 둡니다.
    trim_to_input_length: bool = True


class GrooVAERunner:
    """
    GrooVAE(Magenta MusicVAE) 실제 연결 runner.

    - 입력: NoteSequence (드럼 이벤트가 들어있어야 함)
    - 출력: GrooVAE가 humanize/variation한 NoteSequence

    주의:
    - Magenta/TensorFlow 환경이 맞아야 합니다.
    - config_name / checkpoint_dir을 반드시 맞춰야 합니다.
    """

    def __init__(self, seed: int = 42, model_cfg: Optional[GrooVAEModelConfig] = None):
        self.seed = int(seed)
        self.model_cfg = model_cfg or GrooVAEModelConfig()

        if not self.model_cfg.checkpoint_dir:
            raise ValueError(
                "GrooVAEModelConfig.checkpoint_dir is required. "
                "다운로드한 GrooVAE 체크포인트 폴더 경로를 넣어주세요."
            )

        # Lazy import (환경 안 맞으면 여기서 에러가 납니다)
        try:
            import tensorflow as tf  # noqa: F401
            from magenta.models.music_vae import configs
            from magenta.models.music_vae.trained_model import TrainedModel
        except Exception as e:
            raise ImportError(
                "Magenta GrooVAE를 쓰려면 magenta/tensorflow가 설치되어 있어야 합니다. "
                "현재 환경에서 import 실패했습니다."
            ) from e

        self._tf = __import__("tensorflow")
        self._configs = __import__("magenta.models.music_vae.configs", fromlist=["CONFIG_MAP"])
        self._TrainedModel = __import__(
            "magenta.models.music_vae.trained_model",
            fromlist=["TrainedModel"],
        ).TrainedModel

        if self.model_cfg.config_name not in self._configs.CONFIG_MAP:
            available = list(self._configs.CONFIG_MAP.keys())
            msg = (
                f"Unknown config_name={self.model_cfg.config_name}. "
                f"Available examples (partial): {available[:20]}"
            )
            raise ValueError(msg)

        self._config = self._configs.CONFIG_MAP[self.model_cfg.config_name]

        # 모델 로드
        # 참고: TrainedModel이 내부적으로 TF graph/세션을 다룹니다(버전에 따라 다름).
        # seed는 샘플링 단계에서 사용합니다.
        self._model = self._TrainedModel(
            self._config,
            batch_size=1,
            checkpoint_dir_or_path=self.model_cfg.checkpoint_dir,
        )

    def run(self, ns: music_pb2.NoteSequence) -> music_pb2.NoteSequence:
        """
        ns를 받아 GrooVAE를 적용한 NoteSequence를 반환합니다.
        """
        # 입력이 비어있으면 그대로 반환
        if ns is None or len(ns.notes) == 0:
            return ns

        # Magenta MusicVAE는 보통 "quantized" NoteSequence를 기대합니다.
        # 여기서는 입력이 이미 quantized(16step grid)라고 가정합니다.
        # 아니라면, to_noteseq 단계에서 quantization을 완료해야 합니다.

        # 샘플링 (버전마다 API가 조금 다를 수 있어 가장 무난한 패턴으로 작성)
        # - encode -> decode or sample
        # 드럼 humanize는 흔히 decode(temperature) 쪽이 목적에 맞습니다.
        import numpy as np

        # 재현성
        rng = np.random.default_rng(self.seed)

        # encode
        # encode() 입력은 NoteSequence list를 받는 경우가 많습니다.
        try:
            print(f"DEBUG: Start encoding... (len(ns.notes)={len(ns.notes)})")
            z, _ = self._model.encode([ns])
            print("DEBUG: Encode finished. Start decoding...")
            # decode (temperature 적용)
            out_list = self._model.decode(
                z,
                length=None,  # config 기반 길이(또는 z 기반)
                temperature=float(self.model_cfg.temperature),
            )
            print("DEBUG: Decode finished.")
        except Exception:
            # 버전에 따라 encode/decode 대신 sample을 쓰는 경우가 있어 fallback
            out_list = self._model.sample(
                n=1,
                length=None,
                temperature=float(self.model_cfg.temperature),
            )

        out_ns = out_list[0] if isinstance(out_list, (list, tuple)) else out_list

        if not isinstance(out_ns, music_pb2.NoteSequence):
            raise TypeError(f"GrooVAE output type is not NoteSequence: {type(out_ns)}")

        # 입력 길이에 맞춰 자르기(선택)
        if self.model_cfg.trim_to_input_length:
            out_ns = self._trim_noteseq_to_input(out_ns, ns)

        return out_ns

    @staticmethod
    def _trim_noteseq_to_input(out_ns: music_pb2.NoteSequence, in_ns: music_pb2.NoteSequence) -> music_pb2.NoteSequence:
        """
        GrooVAE 출력이 2bar/4bar 고정으로 나오는 경우가 많아서,
        입력의 끝시간에 맞춰 잘라주는 간단한 후처리.
        """
        # 입력 끝시간(초)
        if len(in_ns.notes) == 0:
            return out_ns

        in_end = max(n.end_time for n in in_ns.notes)
        # 노트/컨트롤 제거
        trimmed = music_pb2.NoteSequence()
        trimmed.CopyFrom(out_ns)

        # notes
        kept_notes = []
        for n in trimmed.notes:
            if n.start_time < in_end + 1e-6:
                # end_time도 입력 끝을 넘으면 clamp
                if n.end_time > in_end:
                    n.end_time = in_end
                kept_notes.append(n)

        # notes 필드 재구성
        del trimmed.notes[:]
        trimmed.notes.extend(kept_notes)

        # total_time 업데이트
        trimmed.total_time = min(trimmed.total_time, in_end)
        return trimmed