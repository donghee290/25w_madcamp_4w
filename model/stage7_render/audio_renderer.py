# stage7_render/audio_renderer.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import librosa
import numpy as np
import soundfile as sf


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


def _safe_bar_step(grid_json: Dict[str, Any], bar: int, step: int) -> tuple[int, int]:
    """
    grid_json["t_step"][bar][step] 접근이 항상 안전하도록 bar/step을 보정합니다.
    """
    t_step = grid_json.get("t_step", None)
    if not isinstance(t_step, list) or not t_step:
        # t_step이 없으면 최소한 bar/step 음수만 방지
        return max(0, bar), max(0, step)

    bar = max(0, min(int(bar), len(t_step) - 1))
    row = t_step[bar]
    if not isinstance(row, list) or not row:
        return bar, 0

    step = int(step) % len(row)
    return bar, step


def playback_time(grid_json: Dict[str, Any], ev: Dict[str, Any]) -> float:
    """
    재생 시간(sec): grid 스텝 기준 시간 + micro_offset_ms
    - grid_json["t_step"]를 최우선으로 사용
    - bar/step 인덱스 방어 포함
    """
    bar, step = _safe_bar_step(grid_json, int(ev.get("bar", 0)), int(ev.get("step", 0)))

    t_step = grid_json.get("t_step", None)
    if isinstance(t_step, list) and t_step and isinstance(t_step[bar], list) and t_step[bar]:
        base = float(t_step[bar][step])
    else:
        # fallback: t_step이 없을 때만 사용하는 단순 계산
        tbar = float(grid_json.get("tbar", 0.0) or 0.0)
        tstep = float(grid_json.get("tstep", 0.0) or 0.0)
        base = bar * tbar + step * tstep

    micro_ms = 0.0  # ALWAYS 0.0 per user request
    return base + micro_ms / 1000.0


def ui_snap_info(grid_json: Dict[str, Any], ev: Dict[str, Any]) -> Dict[str, Any]:
    """
    UI 표시에 사용할 스냅 정보.
    out-of-range를 방지하기 위해 bar/step을 안전 보정합니다.
    """
    bar, step = _safe_bar_step(grid_json, int(ev.get("bar", 0)), int(ev.get("step", 0)))
    t_step = grid_json.get("t_step", None)

    if isinstance(t_step, list) and t_step and isinstance(t_step[bar], list) and t_step[bar]:
        snapped = float(t_step[bar][step])
    else:
        tbar = float(grid_json.get("tbar", 0.0) or 0.0)
        tstep = float(grid_json.get("tstep", 0.0) or 0.0)
        snapped = bar * tbar + step * tstep

    return {"ui_bar": bar, "ui_step": step, "ui_time_sec": snapped}


def _resolve_sample_path(
    ev: Dict[str, Any],
    sample_root: Path,
    sample_id: Optional[str],
) -> Optional[Path]:
    """
    이벤트에서 실제 원샷 파일을 찾습니다.
    1) ev["filepath"]가 존재하고 실제 파일이면 사용
    2) sample_root / f"{sample_id}{ext}" 탐색
    """
    wav_path: Optional[Path] = None

    # 1) filepath 필드 우선
    path_str = (ev.get("filepath", "") or "").strip()
    if path_str:
        p = Path(path_str)
        if p.exists():
            return p

    # 2) sample_id 기반 탐색
    if sample_id:
        for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
            p = sample_root / f"{sample_id}{ext}"
            if p.exists():
                wav_path = p
                break

    return wav_path


def render_events(
    grid_json: Dict[str, Any],
    events: List[Dict[str, Any]],
    sample_root: Path,
    out_wav: Path,
    target_sr: int = 44100,
    master_gain: float = 0.9,
    fade_ms: float = 5.0,
    clamp_micro_to_half_step: bool = True,
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

    # Check consistency: max(bar) in events vs num_bars
    max_event_bar = 0
    if events:
        max_event_bar = max(int(e.get("bar", 0)) for e in events)
    
    if max_event_bar >= num_bars:
        print(f"[WARN] max_event_bar ({max_event_bar}) >= grid num_bars ({num_bars}). Auto-expanding.")
        num_bars = max_event_bar + 1

    total_sec = num_bars * tbar
    total_samples = int(round(total_sec * target_sr)) + 1

    mix = np.zeros(total_samples, dtype=np.float32)

    # micro_offset 안전 제한(선택)
    half_step_ms = (tstep * 0.5) * 1000.0 if tstep > 0 else 0.0

    for ev in events:
        sample_id = ev.get("sample_id")

        # velocity
        vel = float(ev.get("vel", 1.0) or 1.0)
        if "velocity" in ev and ev["velocity"] is not None:
            # MIDI velocity (0..127)
            vel = float(ev["velocity"]) / 127.0
        vel = _clamp(vel, 0.0, 1.5)  # 약간의 headroom

        # duration
        dur_steps = int(ev.get("dur_steps", 1) or 1)
        dur_steps = max(1, dur_steps)

        # micro
        # micro_ms = float(ev.get("micro_offset_ms", 0.0) or 0.0)
        micro_ms = 0.0

        # sample path
        wav_path = _resolve_sample_path(ev, sample_root=sample_root, sample_id=sample_id)
        if wav_path is None:
            print(f"[WARN] sample not found for id: {sample_id} (filepath: {ev.get('filepath')}) in root: {sample_root}")
            continue

        y = load_wav_mono(wav_path, target_sr)

        # duration 컷 (grid 기반)
        max_len = int(round(dur_steps * tstep * target_sr)) if tstep > 0 else 0
        if max_len > 0 and len(y) > max_len:
            y = y[:max_len]

        # fade로 클릭 방지
        y = apply_fade(y, fade_ms=fade_ms, sr=target_sr)

        # apply velocity
        y = y * vel

        # === 타임 계산 (핵심) ===
        # grid.t_step 기반 + micro_offset
        # bar/step 인덱스 방어
        # ev_for_time = dict(ev)
        # ev_for_time["micro_offset_ms"] = 0.0
        # ev_for_time["micro_offset_ms"] = micro_ms  # clamp된 값 사용
        t = playback_time(grid_json, ev)

        # 음수 방지
        if t < 0:
            t = 0.0

        # sample index는 round가 덜 한쪽으로 치우침
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