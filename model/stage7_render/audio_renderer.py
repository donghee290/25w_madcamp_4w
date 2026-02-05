# stage7_render/audio_renderer.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import librosa
import numpy as np
import soundfile as sf


AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a")


def load_wav_mono(path: Path, target_sr: int) -> np.ndarray:
    y, _sr = librosa.load(path, sr=target_sr, mono=True)
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


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _ensure_t_step_extended(grid_json: Dict[str, Any], num_bars: int) -> None:
    """
    events의 bar 범위를 커버하도록 grid_json["t_step"]를 num_bars까지 확장합니다.
    - 기존 row는 유지하고, 부족한 bar row만 추가합니다.
    """
    if num_bars <= 0:
        return

    tbar = float(grid_json.get("tbar", 0.0) or 0.0)
    tstep = float(grid_json.get("tstep", 0.0) or 0.0)
    steps_per_bar = int(grid_json.get("steps_per_bar", 16) or 16)

    if tbar <= 0 or tstep <= 0 or steps_per_bar <= 0:
        return

    t_step = grid_json.get("t_step", None)
    if not isinstance(t_step, list):
        t_step = []
        grid_json["t_step"] = t_step

    cur = len(t_step)
    if cur >= num_bars:
        return

    for b in range(cur, num_bars):
        base = b * tbar
        row = [base + k * tstep for k in range(steps_per_bar)]
        t_step.append(row)


def playback_time(grid_json: Dict[str, Any], ev: Dict[str, Any]) -> float:
    """
    재생 시간(sec): grid 스텝 기준 시간 (+ micro_offset_ms)
    IMPORTANT:
    - progressive처럼 bar가 길게 늘어난 경우에도 bar를 clamp 하지 않습니다.
    - t_step 범위 밖이면 공식(bar*tbar + step*tstep)으로 계산합니다.
    - micro_offset은 현재 0으로 고정(동바님 요청).
    """
    bar = int(ev.get("bar", 0) or 0)
    step = int(ev.get("step", 0) or 0)

    tbar = float(grid_json.get("tbar", 0.0) or 0.0)
    tstep = float(grid_json.get("tstep", 0.0) or 0.0)

    t_step = grid_json.get("t_step", None)
    if isinstance(t_step, list) and 0 <= bar < len(t_step) and isinstance(t_step[bar], list) and t_step[bar]:
        row = t_step[bar]
        step = step % len(row)
        base = float(row[step])
    else:
        base = bar * tbar + step * tstep

    micro_ms = 0.0
    return base + micro_ms / 1000.0


def ui_snap_info(grid_json: Dict[str, Any], ev: Dict[str, Any]) -> Dict[str, Any]:
    """
    UI 표시용 스냅 정보.
    - t_step이 있으면 그 기준
    - 없거나 범위 밖이면 공식 계산
    """
    bar = int(ev.get("bar", 0) or 0)
    step = int(ev.get("step", 0) or 0)

    tbar = float(grid_json.get("tbar", 0.0) or 0.0)
    tstep = float(grid_json.get("tstep", 0.0) or 0.0)

    t_step = grid_json.get("t_step", None)
    if isinstance(t_step, list) and 0 <= bar < len(t_step) and isinstance(t_step[bar], list) and t_step[bar]:
        row = t_step[bar]
        step = step % len(row)
        snapped = float(row[step])
    else:
        snapped = bar * tbar + step * tstep

    return {"ui_bar": bar, "ui_step": step, "ui_time_sec": snapped}


def _resolve_sample_path(
    ev: Dict[str, Any],
    sample_root: Path,
    sample_id: Optional[str],
) -> Optional[Path]:
    """
    이벤트에서 실제 파일을 찾습니다.
    1) ev["filepath"]가 존재하고 실제 파일이면 사용
    2) sample_root / f"{sample_id}{ext}" 탐색
    """
    # 1) filepath 필드 우선
    path_str = (ev.get("filepath", "") or "").strip()
    if path_str:
        p = Path(path_str)
        if p.exists():
            return p

    # 2) sample_id 기반 탐색
    if sample_id:
        for ext in AUDIO_EXTS:
            p = sample_root / f"{sample_id}{ext}"
            if p.exists():
                return p

    return None


def render_events(
    grid_json: Dict[str, Any],
    events: List[Dict[str, Any]],
    sample_root: Path,
    out_wav: Path,
    target_sr: int = 44100,
    master_gain: float = 0.9,
    fade_ms: float = 5.0,
) -> None:
    """
    sample_root: 원샷 wav들이 있는 디렉토리 (filepath 기준 상대/절대 모두 처리)
    """

    # grid 정보
    num_bars = int(grid_json.get("num_bars", 0) or 0)
    tbar = float(grid_json.get("tbar", 0.0) or 0.0)
    tstep = float(grid_json.get("tstep", 0.0) or 0.0)

    if num_bars <= 0 or tbar <= 0:
        raise ValueError("grid_json must contain valid num_bars and tbar")

    # events가 progressive로 늘어난 경우 grid를 확장
    max_event_bar = 0
    if events:
        max_event_bar = max(int(e.get("bar", 0) or 0) for e in events)

    if max_event_bar >= num_bars:
        print(f"[WARN] max_event_bar ({max_event_bar}) >= grid num_bars ({num_bars}). Auto-expanding.")
        num_bars = max_event_bar + 1
        grid_json["num_bars"] = num_bars  # grid_json에도 반영

    # t_step을 num_bars까지 확장(이게 8초 문제의 핵심 해결)
    _ensure_t_step_extended(grid_json, num_bars)

    total_sec = num_bars * tbar
    total_samples = int(round(total_sec * target_sr)) + 1

    mix = np.zeros(total_samples, dtype=np.float32)

    for ev in events:
        sample_id = ev.get("sample_id")
        role = str(ev.get("role", "") or "").upper()

        # velocity
        vel = float(ev.get("vel", 1.0) or 1.0)
        if "velocity" in ev and ev["velocity"] is not None:
            vel = float(ev["velocity"]) / 127.0  # MIDI velocity (0..127)
        vel = _clamp(vel, 0.0, 1.5)  # 약간의 headroom

        # duration
        dur_steps = int(ev.get("dur_steps", 1) or 1)
        dur_steps = max(1, dur_steps)

        # micro (현재 0 고정)
        # micro_ms = float(ev.get("micro_offset_ms", 0.0) or 0.0)
        micro_ms = 0.0
        _ = micro_ms  # unused (kept for readability)

        # sample path
        wav_path = _resolve_sample_path(ev, sample_root=sample_root, sample_id=sample_id)
        if wav_path is None:
            print(f"[WARN] sample not found for id: {sample_id} (filepath: {ev.get('filepath')}) in root: {sample_root}")
            continue

        y = load_wav_mono(wav_path, target_sr)

        # duration 컷 (grid 기반)
        # FIX: Percussive roles (CORE, ACCENT, MOTION, FILL) should be One-Shot (not gated by step duration)
        # unless explicitly requested longer duration? For now, we assume simple beats.
        # TEXTURE is usually gated.
        is_percussive = role in ["CORE", "ACCENT", "MOTION", "FILL", "KICK", "SNARE", "HIHAT"]
        
        max_len = int(round(dur_steps * tstep * target_sr)) if tstep > 0 else 0
        
        if not is_percussive and max_len > 0 and len(y) > max_len:
             y = y[:max_len]

        # TEXTURE: 짧은 샘플이면 해당 dur_steps 길이만큼 루프해서 깔기
        # (texture는 대개 배경음이라 "한 마디/여러 스텝 지속"이 자연스러움)
        if role == "TEXTURE" and max_len > 0 and len(y) < max_len:
            reps = (max_len + len(y) - 1) // len(y)
            y = np.tile(y, reps)[:max_len]

        # fade로 클릭 방지
        y = apply_fade(y, fade_ms=fade_ms, sr=target_sr)

        # apply velocity
        y = y * vel

        # 타임 계산(핵심): bar clamp 금지 + t_step 부족 시 공식 계산
        t = playback_time(grid_json, ev)
        if t < 0:
            t = 0.0

        start = int(round(t * target_sr))
        if start < 0 or start >= total_samples:
            continue

        end = min(start + len(y), total_samples)
        mix[start:end] += y[: end - start]

    # 마스터 노멀라이즈 (hard clip 방지)
    peak = float(np.max(np.abs(mix)) + 1e-9)
    if peak > 1.0:
        mix /= peak
    mix *= float(master_gain)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_wav, mix, target_sr)
    print(f"[OK] rendered: {out_wav}")


def render_wav_from_event_grid(
    grid_json_path: str,
    event_grid_json_path: str,
    sample_root: str,
    out_wav: str,
    target_sr: int = 44100,
) -> None:
    """Wrapper to load JSONs and call render_events."""
    grid = json.loads(Path(grid_json_path).read_text(encoding="utf-8"))
    events = json.loads(Path(event_grid_json_path).read_text(encoding="utf-8"))

    render_events(
        grid_json=grid,
        events=events,
        sample_root=Path(sample_root),
        out_wav=Path(out_wav),
        target_sr=target_sr,
    )