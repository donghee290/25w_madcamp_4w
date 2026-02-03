# stage7_render/audio_renderer.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import soundfile as sf
import librosa


def load_wav_mono(path: Path, target_sr: int) -> np.ndarray:
    y, sr = librosa.load(path, sr=target_sr, mono=True)
    return y.astype(np.float32, copy=False)


def apply_fade(y: np.ndarray, fade_ms: float, sr: int) -> np.ndarray:
    if fade_ms <= 0:
        return y
    n = int(sr * fade_ms / 1000.0)
    if n <= 1 or n * 2 >= len(y):
        return y
    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
    fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
    y[:n] *= fade_in
    y[-n:] *= fade_out
    return y


def render_events(
    grid_json: Dict,
    events: List[Dict],
    sample_root: Path,
    out_wav: Path,
    target_sr: int = 44100,
    master_gain: float = 0.9,
) -> None:
    """
    sample_root: 원샷 wav들이 있는 디렉토리 (filepath 기준 상대/절대 모두 처리)
    """

    num_bars = int(grid_json["num_bars"])
    tbar = float(grid_json["tbar"])
    tstep = float(grid_json["tstep"])

    total_sec = num_bars * tbar
    total_samples = int(total_sec * target_sr) + 1

    mix = np.zeros(total_samples, dtype=np.float32)

    for ev in events:
        role = ev.get("role", "unknown")
        sample_id = ev.get("sample_id")
        step = int(ev.get("step", 0))
        bar = int(ev.get("bar", 0))
        vel = float(ev.get("vel", 1.0))
        # velocity key variation
        if "velocity" in ev:
            vel = float(ev["velocity"]) / 127.0
        
        dur_steps = int(ev.get("dur_steps", 1))
        micro_ms = float(ev.get("micro_offset_ms", 0.0))

        # 원샷 파일 경로
        # sample_id.wav or sample_id.mp3 등 → 실제 파일은 pools.json에서 왔으므로
        # filepath를 event에 넣었으면 그걸 쓰는 게 제일 정확
        # MVP: sample_id로 wav 찾기
        wav_path = None
        
        # 1. filepath 필드 확인
        path_str = ev.get("filepath", "") or ""
        if path_str.strip():
            p = Path(path_str)
            if p.exists():
                wav_path = p
        
        # 2. sample_id로 sample_root에서 탐색
        if wav_path is None and sample_id:
            for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
                p = sample_root / f"{sample_id}{ext}"
                if p.exists():
                    wav_path = p
                    break
        
        if wav_path is None:
            print(f"[WARN] sample not found for id: {sample_id} (path_str: {path_str}) in root: {sample_root}")
            continue
        
        # print(f"[DEBUG] Valid sample: {wav_path}")

        y = load_wav_mono(wav_path, target_sr)

        # duration 컷
        max_len = int(dur_steps * tstep * target_sr)
        if max_len > 0 and len(y) > max_len:
            y = y[:max_len]

        # fade로 클릭 방지
        y = apply_fade(y, fade_ms=5.0, sr=target_sr)

        # velocity
        y = y * vel

        # 타임 계산
        t = bar * tbar + step * tstep + micro_ms / 1000.0
        start = int(t * target_sr)

        if start < 0 or start >= total_samples:
            continue

        end = min(start + len(y), total_samples)
        mix[start:end] += y[: end - start]

    # 마스터 노멀라이즈 (hard clip 방지)
    peak = np.max(np.abs(mix)) + 1e-9
    if peak > 1.0:
        mix /= peak
    mix *= master_gain

    sf.write(out_wav, mix, target_sr)
    print(f"[OK] rendered: {out_wav}")
