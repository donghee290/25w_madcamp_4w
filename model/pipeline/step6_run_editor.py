# pipeline/run_editor.py
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
import sys
# Add model dir to sys.path
sys.path.append(str(Path(__file__).parent.parent))


# ----------------------------
# Utilities
# ----------------------------
def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def get_next_version(out_dir: Path, prefix: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob(f"{prefix}_*.json"))
    max_ver = 0
    for p in existing:
        try:
            stem = p.stem  # prefix_{n}
            parts = stem.split("_")
            if len(parts) >= 2 and parts[-1].isdigit():
                max_ver = max(max_ver, int(parts[-1]))
        except Exception:
            pass
    return max_ver + 1


def role_to_family(role: str) -> str:
    """
    프로젝트 내부 role (CORE/ACCENT/MOTION/FILL/TEXTURE) 또는
    drum voice role (kick/snare/hat/tom/texture 등)을 모두 받아
    "family"로 묶기 위한 함수.
    """
    r = str(role).strip().lower()
    if r in ("core", "kick"):
        return "core"
    if r in ("accent", "snare"):
        return "accent"
    if r in ("motion", "hat", "hihat", "hh", "closed_hat", "closed-hat"):
        return "motion"
    if r in ("fill", "tom", "toms"):
        return "fill"
    if r in ("texture", "noise", "fx", "amb", "ambient"):
        return "texture"
    # 알 수 없으면 그대로
    return r


def ensure_micro_offset_ms(e: Dict[str, Any], rng: random.Random, max_abs_ms: int = 25) -> None:
    """
    micro_offset_ms가 없으면 생성(간단 버전).
    - groove 모델을 쓰면 그 결과를 그대로 넣고,
    - 지금은 없을 때만 작은 jitter를 만들어 채움.
    """
    if "micro_offset_ms" in e and e["micro_offset_ms"] is not None:
        return
    e["micro_offset_ms"] = rng.randint(-max_abs_ms, max_abs_ms)


def grid_from_grid_json(grid_json: Dict[str, Any]) -> Tuple[float, float, float, int, int]:
    """
    grid_json에서 필수값을 뽑는다.
    returns: (bpm, tbar, tstep, steps_per_bar, num_bars)
    """
    bpm = float(grid_json["bpm"])
    steps_per_bar = int(grid_json.get("steps_per_bar", 16))
    num_bars = int(grid_json.get("num_bars", grid_json.get("bars", 4)))

    # grid_json에 tbar/tstep이 이미 있으면 우선 사용
    if "tbar" in grid_json and "tstep" in grid_json:
        tbar = float(grid_json["tbar"])
        tstep = float(grid_json["tstep"])
        return bpm, tbar, tstep, steps_per_bar, num_bars

    # 없으면 계산 (meter는 4/4를 기본으로 가정)
    tbeat = 60.0 / bpm
    tbar = 4.0 * tbeat
    tstep = tbar / float(steps_per_bar)
    return bpm, tbar, tstep, steps_per_bar, num_bars


def seconds_to_grid_pos(t: float, tbar: float, tstep: float, steps_per_bar: int) -> Tuple[int, int, float]:
    """
    초 단위 시간을 bar/step으로 근사
    returns: (bar_idx, step_idx, step_float)
    """
    if tbar <= 0 or tstep <= 0:
        return 0, 0, 0.0
    bar_f = t / tbar
    bar = int(math.floor(bar_f))
    in_bar = t - (bar * tbar)
    step_f = in_bar / tstep
    step = int(round(step_f))
    step = max(0, min(steps_per_bar - 1, step))
    return bar, step, step_f


def grid_pos_to_seconds(bar: int, step: int, tbar: float, tstep: float) -> float:
    return (float(bar) * tbar) + (float(step) * tstep)


# ----------------------------
# Data model
# ----------------------------
@dataclass
class EditorConfig:
    seed: int = 42
    ui_snap: int = 1  # 1이면 UI 표시/저장 시 step 스냅을 적용 (재생 offset은 유지)
    snap_mode: str = "nearest"  # nearest | floor | ceil
    max_micro_offset_ms: int = 25

    # progressive (층 쌓기) 옵션
    progressive: int = 0  # 1이면 core-only -> +accent -> +motion -> +fill -> +texture 순으로 여러 파일 생성
    progressive_prefix: str = "progress"

    # export 옵션
    export_midi: int = 1
    midi_ppq: int = 480

    # preview render 옵션
    render_preview: int = 0
    sample_root: Optional[Path] = None
    target_sr: int = 44100


# ----------------------------
# Editor operations
# ----------------------------
def apply_ui_snap(
    events: List[Dict[str, Any]],
    tbar: float,
    tstep: float,
    steps_per_bar: int,
    snap_mode: str = "nearest",
) -> List[Dict[str, Any]]:
    """
    저장되는 event_grid.json을 "UI 표시 기준"으로 스냅.
    단, micro_offset_ms는 그대로 둔다.
    - start/end는 step 경계로 조정
    - offset 필드가 있으면 유지
    """
    out: List[Dict[str, Any]] = []
    for e in events:
        e2 = dict(e)

        start = float(e2.get("start", 0.0))
        end = float(e2.get("end", start + tstep))

        bar, step, step_f = seconds_to_grid_pos(start, tbar, tstep, steps_per_bar)

        if snap_mode == "floor":
            step = int(math.floor(step_f))
        elif snap_mode == "ceil":
            step = int(math.ceil(step_f))
        else:
            step = int(round(step_f))

        step = max(0, min(steps_per_bar - 1, step))
        snapped_start = grid_pos_to_seconds(bar, step, tbar, tstep)

        # duration 유지: (end-start)를 step 단위로 반올림
        dur = max(0.0, end - start)
        dur_steps = max(1, int(round(dur / tstep)))
        snapped_end = snapped_start + (dur_steps * tstep)

        e2["start"] = float(snapped_start)
        e2["end"] = float(snapped_end)

        out.append(e2)
    return out


def apply_ops(events: List[Dict[str, Any]], ops: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    간단한 ops 포맷을 지원.
    ops 예:
    {
      "global": {"vel_mul": 0.9, "vel_add": -5},
      "role": {
        "kick": {"vel_mul": 1.05},
        "hat": {"mute": true}
      }
    }
    """
    out = []
    g = ops.get("global", {}) if isinstance(ops, dict) else {}
    role_ops = ops.get("role", {}) if isinstance(ops, dict) else {}

    vel_mul_g = float(g.get("vel_mul", 1.0))
    vel_add_g = float(g.get("vel_add", 0.0))

    for e in events:
        e2 = dict(e)
        role = str(e2.get("role", ""))
        ro = role_ops.get(role, {}) if isinstance(role_ops, dict) else {}

        if ro.get("mute", False) is True:
            continue

        vel = float(e2.get("velocity", 0.0))
        vel = vel * vel_mul_g + vel_add_g

        vel_mul_r = float(ro.get("vel_mul", 1.0))
        vel_add_r = float(ro.get("vel_add", 0.0))
        vel = vel * vel_mul_r + vel_add_r

        e2["velocity"] = int(clamp(round(vel), 1, 127))
        out.append(e2)

    return out


def progressive_layers(events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    family 기준으로 층을 쌓는다.
    반환:
      {
        "1_core": [...],
        "2_core_accent": [...],
        ...
      }
    """
    core = []
    accent = []
    motion = []
    fill = []
    texture = []
    other = []

    for e in events:
        fam = role_to_family(e.get("role", ""))
        if fam == "core":
            core.append(e)
        elif fam == "accent":
            accent.append(e)
        elif fam == "motion":
            motion.append(e)
        elif fam == "fill":
            fill.append(e)
        elif fam == "texture":
            texture.append(e)
        else:
            other.append(e)

    # other는 마지막에 붙인다(원하면 나중에 분리)
    out: Dict[str, List[Dict[str, Any]]] = {}
    out["1_core"] = core[:]
    out["2_core_accent"] = core[:] + accent[:]
    out["3_core_accent_motion"] = core[:] + accent[:] + motion[:]
    out["4_core_accent_motion_fill"] = core[:] + accent[:] + motion[:] + fill[:]
    out["5_full_plus_texture"] = core[:] + accent[:] + motion[:] + fill[:] + texture[:] + other[:]
    return out


# ----------------------------
# MIDI export
# ----------------------------
GM_DRUM_MAP = {
    "core": 35,      # kick
    "accent": 38,    # snare
    "motion": 42,    # closed hat
    "fill": 45,      # low tom
    "texture": 49,   # crash (임시)
}

ROLE_TO_MIDI_PITCH_FALLBACK = {
    "kick": 35,
    "snare": 38,
    "hat": 42,
    "tom": 45,
    "texture": 49,
}


def export_midi(events: List[Dict[str, Any]], grid_json: Dict[str, Any], out_mid: Path, ppq: int = 480) -> None:
    """
    note-seq/magenta 없이 MIDI만 뽑는 용도.
    """
    try:
        import mido  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "mido가 설치되어 있지 않습니다. requirements에 mido 추가 후 다시 실행하세요."
        ) from e

    bpm, tbar, tstep, steps_per_bar, num_bars = grid_from_grid_json(grid_json)

    mid = mido.MidiFile(ticks_per_beat=int(ppq))
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # tempo
    tempo = mido.bpm2tempo(bpm)  # microseconds per beat
    track.append(mido.MetaMessage("set_tempo", tempo=int(tempo), time=0))

    # events -> absolute time seconds
    # micro_offset_ms는 재생 느낌용이지만, MIDI에도 반영 가능(선택). 여기서는 반영한다.
    notes = []
    for e in events:
        start = float(e.get("start", 0.0))
        end = float(e.get("end", start + tstep))
        micro = float(e.get("micro_offset_ms", 0.0)) / 1000.0
        start_t = max(0.0, start + micro)
        end_t = max(start_t + 1e-4, end + micro)

        vel = int(clamp(int(e.get("velocity", 80)), 1, 127))
        role = str(e.get("role", "")).strip()
        fam = role_to_family(role)

        pitch = e.get("pitch", None)
        if pitch is None:
            pitch = GM_DRUM_MAP.get(fam, ROLE_TO_MIDI_PITCH_FALLBACK.get(role.lower(), 42))
        pitch = int(pitch)

        is_drum = bool(e.get("is_drum", True))

        notes.append((start_t, end_t, pitch, vel, is_drum))

    notes.sort(key=lambda x: (x[0], x[2]))

    # seconds -> ticks
    # ticks = seconds * ticks_per_beat / seconds_per_beat
    seconds_per_beat = 60.0 / bpm
    def sec_to_ticks(sec: float) -> int:
        return int(round(sec * (ppq / seconds_per_beat)))

    # build note_on/note_off with delta times
    msgs = []
    for (st, et, pitch, vel, is_drum) in notes:
        st_ticks = sec_to_ticks(st)
        et_ticks = sec_to_ticks(et)
        ch = 9 if is_drum else 0
        msgs.append((st_ticks, True, ch, pitch, vel))
        msgs.append((et_ticks, False, ch, pitch, 0))

    msgs.sort(key=lambda x: (x[0], 0 if x[1] else 1, x[3]))  # note_on 먼저

    last = 0
    for t, is_on, ch, pitch, vel in msgs:
        dt = max(0, t - last)
        last = t
        if is_on:
            track.append(mido.Message("note_on", channel=int(ch), note=int(pitch), velocity=int(vel), time=int(dt)))
        else:
            track.append(mido.Message("note_off", channel=int(ch), note=int(pitch), velocity=0, time=int(dt)))

    mid.save(str(out_mid))


# ----------------------------
# Preview render (optional)
# ----------------------------
def try_render_preview(
    grid_json: Dict[str, Any],
    events: List[Dict[str, Any]],
    sample_root: Path,
    out_wav: Path,
    target_sr: int,
) -> None:
    """
    기존 프로젝트에 있는 render_events를 그대로 활용.
    - sample_id -> wav 파일을 sample_root에서 찾는 로직은 render.py가 담당한다고 가정.
    """
    from stage7_render.audio_renderer import render_events

    render_events(
        grid_json=grid_json,
        events=events,
        sample_root=sample_root,
        out_wav=out_wav,
        target_sr=int(target_sr),
    )


# ----------------------------
# CLI
# ----------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()

    p.add_argument("--grid_json", type=str, required=True)
    p.add_argument("--event_grid", type=str, required=True)
    p.add_argument("--out_dir", type=str, required=True)

    # 편집 옵션
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--ui_snap", type=int, default=1, help="1이면 저장 이벤트 start/end를 step에 스냅(표시용). micro_offset_ms는 유지")
    p.add_argument("--snap_mode", type=str, default="nearest", choices=["nearest", "floor", "ceil"])
    p.add_argument("--max_micro_offset_ms", type=int, default=25)

    # ops
    p.add_argument("--ops_json", type=str, default="", help="편집 연산(velocity/mute 등) 정의한 ops json 경로(선택)")

    # progressive
    p.add_argument("--progressive", type=int, default=0, help="1이면 core->+accent->... 층별로 여러 파일 생성")
    p.add_argument("--progress_prefix", type=str, default="progress")

    # export
    p.add_argument("--export_midi", type=int, default=1)
    p.add_argument("--midi_ppq", type=int, default=480)

    # preview render
    p.add_argument("--render_preview", type=int, default=0)
    p.add_argument("--sample_root", type=str, default="", help="원샷 wav 루트 디렉토리(선택)")
    p.add_argument("--target_sr", type=int, default=44100)

    return p.parse_args()


def main() -> None:
    args = parse_args()

    cfg = EditorConfig(
        seed=int(args.seed),
        ui_snap=int(args.ui_snap),
        snap_mode=str(args.snap_mode),
        max_micro_offset_ms=int(args.max_micro_offset_ms),
        progressive=int(args.progressive),
        progressive_prefix=str(args.progress_prefix),
        export_midi=int(args.export_midi),
        midi_ppq=int(args.midi_ppq),
        render_preview=int(args.render_preview),
        sample_root=Path(args.sample_root) if args.sample_root else None,
        target_sr=int(args.target_sr),
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grid_path = Path(args.grid_json)
    ev_path = Path(args.event_grid)

    grid_json: Dict[str, Any] = load_json(grid_path)
    events_in: List[Dict[str, Any]] = load_json(ev_path)

    bpm, tbar, tstep, steps_per_bar, num_bars = grid_from_grid_json(grid_json)

    rng = random.Random(cfg.seed)

    # 1) micro_offset_ms 보정 (없으면 생성)
    events = []
    for e in events_in:
        e2 = dict(e)
        ensure_micro_offset_ms(e2, rng, max_abs_ms=cfg.max_micro_offset_ms)
        events.append(e2)

    # 2) ops 적용 (선택)
    if args.ops_json:
        ops = load_json(Path(args.ops_json))
        events = apply_ops(events, ops)

    # 3) UI 스냅(저장용) (선택)
    if cfg.ui_snap == 1:
        events = apply_ui_snap(events, tbar=tbar, tstep=tstep, steps_per_bar=steps_per_bar, snap_mode=cfg.snap_mode)

    # 4) 출력 버전 번호
    ver = get_next_version(out_dir, prefix="event_grid")
    base_event = out_dir / f"event_grid_{ver}.json"
    base_mid = out_dir / f"event_grid_{ver}.mid"
    base_wav = out_dir / f"preview_{ver}.wav"

    # 5) progressive가 아니면 단일 저장
    if cfg.progressive != 1:
        save_json(base_event, events)

        print("[DONE] editor saved")
        print(" - event_grid:", str(base_event))
        print(" - num_events:", len(events))

        if cfg.export_midi == 1:
            export_midi(events, grid_json, base_mid, ppq=cfg.midi_ppq)
            print(" - midi:", str(base_mid))

        if cfg.render_preview == 1:
            sample_root = cfg.sample_root or Path("examples/input_samples")
            try_render_preview(grid_json=grid_json, events=events, sample_root=sample_root, out_wav=base_wav, target_sr=cfg.target_sr)
            print(" - preview_wav:", str(base_wav))

        return

    # 6) progressive 저장: core-only -> +accent -> ...
    layers = progressive_layers(events)
    meta = {
        "seed": cfg.seed,
        "ui_snap": cfg.ui_snap,
        "snap_mode": cfg.snap_mode,
        "bpm": bpm,
        "steps_per_bar": steps_per_bar,
        "num_bars": num_bars,
        "layer_keys": list(layers.keys()),
    }

    meta_path = out_dir / f"{cfg.progressive_prefix}_meta_{ver}.json"
    save_json(meta_path, meta)

    print("[INFO] progressive export enabled")
    print(" - meta:", str(meta_path))

    for i, (k, evs) in enumerate(layers.items(), start=1):
        p_json = out_dir / f"{cfg.progressive_prefix}_{k}_{ver}.json"
        save_json(p_json, evs)
        print(f" - layer[{i}] {k}: {p_json} (n={len(evs)})")

        if cfg.export_midi == 1:
            p_mid = out_dir / f"{cfg.progressive_prefix}_{k}_{ver}.mid"
            export_midi(evs, grid_json, p_mid, ppq=cfg.midi_ppq)

        if cfg.render_preview == 1:
            p_wav = out_dir / f"{cfg.progressive_prefix}_{k}_{ver}.wav"
            sample_root = cfg.sample_root or Path("examples/input_samples")
            try_render_preview(grid_json=grid_json, events=evs, sample_root=sample_root, out_wav=p_wav, target_sr=cfg.target_sr)

    print("[DONE] progressive editor export complete")


if __name__ == "__main__":
    main()