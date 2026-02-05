from __future__ import annotations

from typing import Dict, List, Any, Tuple
from pathlib import Path

import mido

from .types import Grid, Event


def role_to_drum_pitch(role: str) -> int:
    r = role.upper()
    if r == "CORE":
        return 36  # kick
    if r == "ACCENT":
        return 38  # snare
    if r == "MOTION":
        return 42  # closed hat
    if r == "FILL":
        return 45  # low tom
    if r == "TEXTURE":
        return 49  # crash (대충)
    return 39  # clap-ish


def sec_to_ticks(t: float, ticks_per_beat: int, bpm: float) -> int:
    # 1 beat = 60/bpm sec
    sec_per_beat = 60.0 / float(bpm)
    ticks = int(round((t / sec_per_beat) * ticks_per_beat))
    return max(0, ticks)


def export_event_grid_to_midi(
    grid: Grid,
    events: List[Event],
    out_mid: str | Path,
    ticks_per_beat: int = 480,
) -> None:
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # tempo
    tempo = mido.bpm2tempo(grid.bpm)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    # drum channel = 9 (0-based)
    drum_ch = 9

    # 이벤트를 절대시간(초)로 변환 후 tick으로 정렬
    notes: List[Tuple[int, int, int]] = []  # (tick, pitch, vel)
    note_offs: List[Tuple[int, int]] = []   # (tick, pitch)

    for e in events:
        base_t = grid.t_step[e.bar][e.step]
        t = base_t + (float(e.micro_offset_ms) / 1000.0)
        tick_on = sec_to_ticks(t, ticks_per_beat, grid.bpm)

        pitch = role_to_drum_pitch(e.role)
        vel = int(round(max(1, min(127, e.vel * 127.0))))

        # dur
        t_off = t + (max(1, int(e.dur_steps)) * grid.tstep)
        tick_off = sec_to_ticks(t_off, ticks_per_beat, grid.bpm)
        if tick_off <= tick_on:
            tick_off = tick_on + 1

        notes.append((tick_on, pitch, vel))
        note_offs.append((tick_off, pitch))

    # 합쳐서 시간순으로 메시지 뽑기 (note_on/off 모두)
    msgs: List[Tuple[int, mido.Message]] = []
    for tick_on, pitch, vel in notes:
        msgs.append((tick_on, mido.Message("note_on", channel=drum_ch, note=pitch, velocity=vel, time=0)))
    for tick_off, pitch in note_offs:
        msgs.append((tick_off, mido.Message("note_off", channel=drum_ch, note=pitch, velocity=0, time=0)))

    msgs.sort(key=lambda x: x[0])

    # delta time 변환
    last_tick = 0
    for tick, msg in msgs:
        delta = tick - last_tick
        msg.time = max(0, int(delta))
        track.append(msg)
        last_tick = tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    out_mid = Path(out_mid)
    out_mid.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(out_mid))