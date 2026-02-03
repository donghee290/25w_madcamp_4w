"""Structured drum event model and skeleton pattern generators."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .scoring import DrumRole


@dataclass
class DrumEvent:
    """Single drum hit event on the grid."""
    bar: int
    step: int            # 0..15
    role: DrumRole
    sample_id: str       # identifies which sample from the pool
    vel: float           # 0..1
    dur_steps: int = 1   # 1..16
    micro_offset_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "bar": self.bar,
            "step": self.step,
            "role": self.role.value,
            "sample_id": self.sample_id,
            "vel": round(self.vel, 3),
            "dur_steps": self.dur_steps,
            "micro_offset_ms": round(self.micro_offset_ms, 2),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DrumEvent":
        return cls(
            bar=d["bar"],
            step=d["step"],
            role=DrumRole(d["role"]),
            sample_id=d["sample_id"],
            vel=d["vel"],
            dur_steps=d.get("dur_steps", 1),
            micro_offset_ms=d.get("micro_offset_ms", 0.0),
        )


@dataclass
class EventGrid:
    """Complete drum sequence as a list of events."""
    bpm: float
    meter: str = "4/4"
    resolution: int = 16    # steps per bar
    bars: int = 4
    events: List[DrumEvent] = field(default_factory=list)
    kit_dir: str = ""       # path to kit for rendering

    def to_dict(self) -> dict:
        return {
            "bpm": self.bpm,
            "meter": self.meter,
            "resolution": self.resolution,
            "bars": self.bars,
            "kit_dir": self.kit_dir,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EventGrid":
        events = [DrumEvent.from_dict(e) for e in d.get("events", [])]
        return cls(
            bpm=d["bpm"],
            meter=d.get("meter", "4/4"),
            resolution=d.get("resolution", 16),
            bars=d.get("bars", 4),
            events=events,
            kit_dir=d.get("kit_dir", ""),
        )

    def to_json(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def from_json(cls, path: Path) -> "EventGrid":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_midi(self, path: Path) -> None:
        try:
            import pretty_midi
        except ImportError:
            raise ImportError("MIDI export requires pretty_midi. Install: pip install pretty_midi")

        midi = pretty_midi.PrettyMIDI(initial_tempo=self.bpm)
        drum = pretty_midi.Instrument(program=0, is_drum=True, name="DrumGenX")

        role_midi = {
            DrumRole.CORE: 36,      # Bass Drum 1
            DrumRole.ACCENT: 38,    # Acoustic Snare
            DrumRole.MOTION: 42,    # Closed Hi-Hat
            DrumRole.FILL: 45,      # Low Tom
            DrumRole.TEXTURE: 49,   # Crash Cymbal 1
        }

        for event in self.events:
            midi_note = role_midi.get(event.role, 36)
            t_start = self.event_time(event)
            t_end = t_start + self.t_step * event.dur_steps
            velocity = max(1, min(127, int(round(1 + 126 * event.vel))))

            note = pretty_midi.Note(
                velocity=velocity,
                pitch=midi_note,
                start=t_start,
                end=t_end,
            )
            drum.notes.append(note)

        midi.instruments.append(drum)
        midi.write(str(path))

    @property
    def t_beat(self) -> float:
        return 60.0 / self.bpm

    @property
    def t_bar(self) -> float:
        return 4 * self.t_beat

    @property
    def t_step(self) -> float:
        return self.t_bar / self.resolution

    def event_time(self, event: DrumEvent) -> float:
        return (event.bar * self.t_bar +
                event.step * self.t_step +
                event.micro_offset_ms / 1000.0)

    def events_at(self, bar: int, step: int) -> List[DrumEvent]:
        return [e for e in self.events if e.bar == bar and e.step == step]

    def add_event(self, event: DrumEvent) -> None:
        self.events.append(event)

    def remove_events(self, bar: int, step: int, role: Optional[DrumRole] = None) -> int:
        before = len(self.events)
        self.events = [
            e for e in self.events
            if not (e.bar == bar and e.step == step and (role is None or e.role == role))
        ]
        return before - len(self.events)

    def apply_max_poly(self, max_poly: int = 3) -> int:
        """Enforce maximum polyphony per step."""
        priority = {
            DrumRole.CORE: 0,
            DrumRole.ACCENT: 1,
            DrumRole.FILL: 2,
            DrumRole.MOTION: 3,
            DrumRole.TEXTURE: 4,
        }

        removed = 0
        new_events = []

        from collections import defaultdict
        groups = defaultdict(list)
        for e in self.events:
            groups[(e.bar, e.step)].append(e)

        for group in groups.values():
            if len(group) <= max_poly:
                new_events.extend(group)
            else:
                group.sort(key=lambda e: priority.get(e.role, 99))
                new_events.extend(group[:max_poly])
                removed += len(group) - max_poly

        self.events = new_events
        return removed


def velocity_for_role(role: DrumRole, energy: float) -> float:
    if role == DrumRole.CORE:
        return float(np.clip(0.60 + 0.40 * energy, 0.0, 1.0))
    if role == DrumRole.ACCENT:
        return float(np.clip(0.70 + 0.30 * energy, 0.0, 1.0))
    if role == DrumRole.MOTION:
        return float(np.clip(0.25 + 0.35 * energy, 0.0, 1.0))
    if role == DrumRole.FILL:
        return float(np.clip(0.75 + 0.25 * energy, 0.0, 1.0))
    if role == DrumRole.TEXTURE:
        return float(np.clip(random.uniform(0.15, 0.35), 0.0, 1.0))
    return 0.5


def select_samples_from_pool(
    pools: Dict[DrumRole, List[str]],
    n_motion: int = 4,
) -> Dict[DrumRole, List[str]]:
    """Select samples from each pool for sequencing."""
    selected = {}

    for role in DrumRole:
        pool = pools.get(role, [])
        if not pool:
            selected[role] = []
            continue

        if role == DrumRole.CORE:
            selected[role] = pool[:min(2, len(pool))]
        elif role == DrumRole.ACCENT:
            selected[role] = pool[:1]
        elif role == DrumRole.MOTION:
            selected[role] = pool[:min(n_motion, len(pool))]
        elif role == DrumRole.FILL:
            selected[role] = pool[:1]
        elif role == DrumRole.TEXTURE:
            selected[role] = pool[:1]

    return selected


def _pick_sample(selected: Dict[DrumRole, List[str]], role: DrumRole, idx: int = 0) -> str:
    pool = selected.get(role, [])
    if not pool:
        return f"{role.value}_default"
    if role == DrumRole.MOTION:
        return pool[idx % len(pool)]
    return pool[idx % len(pool)]


def generate_skeleton(
    bars: int = 4,
    bpm: float = 120.0,
    selected_samples: Optional[Dict[DrumRole, List[str]]] = None,
    sample_energies: Optional[Dict[str, float]] = None,
    motion_density: int = 4,
    kit_dir: str = "",
    seed: int = 42,
) -> EventGrid:
    """Generate skeleton pattern per spec 4-1."""
    rng = random.Random(seed)

    if selected_samples is None:
        selected_samples = {role: [f"{role.value}_001"] for role in DrumRole}
    if sample_energies is None:
        sample_energies = {}

    grid = EventGrid(bpm=bpm, bars=bars, kit_dir=kit_dir)

    motion_idx = 0

    for bar in range(bars):
        for step in [0, 4, 8, 12]:
            sid = _pick_sample(selected_samples, DrumRole.CORE, 0)
            energy = sample_energies.get(sid, 0.5)
            vel = velocity_for_role(DrumRole.CORE, energy)
            grid.add_event(DrumEvent(
                bar=bar, step=step, role=DrumRole.CORE,
                sample_id=sid, vel=vel, dur_steps=1,
            ))

        for step in [4, 12]:
            sid = _pick_sample(selected_samples, DrumRole.ACCENT, 0)
            energy = sample_energies.get(sid, 0.5)
            vel = velocity_for_role(DrumRole.ACCENT, energy)
            grid.add_event(DrumEvent(
                bar=bar, step=step, role=DrumRole.ACCENT,
                sample_id=sid, vel=vel, dur_steps=1,
            ))

        motion_a = [2, 6, 10, 14]
        motion_b = [1, 3, 5, 7, 9, 11, 13, 15]

        motion_steps = list(motion_a)
        b_count = max(0, motion_density - len(motion_a))
        if b_count > 0:
            b_selected = rng.sample(motion_b, min(b_count, len(motion_b)))
            motion_steps.extend(b_selected)

        motion_steps.sort()

        for step in motion_steps:
            sid = _pick_sample(selected_samples, DrumRole.MOTION, motion_idx)
            energy = sample_energies.get(sid, 0.3)
            vel = velocity_for_role(DrumRole.MOTION, energy)
            grid.add_event(DrumEvent(
                bar=bar, step=step, role=DrumRole.MOTION,
                sample_id=sid, vel=vel, dur_steps=1,
            ))
            motion_idx += 1

        if (bar + 1) % 4 == 0:
            fill_steps = rng.sample([12, 13, 14, 15], rng.randint(1, 3))
            fill_steps.sort()
            for step in fill_steps:
                sid = _pick_sample(selected_samples, DrumRole.FILL, 0)
                energy = sample_energies.get(sid, 0.5)
                vel = velocity_for_role(DrumRole.FILL, energy)
                grid.add_event(DrumEvent(
                    bar=bar, step=step, role=DrumRole.FILL,
                    sample_id=sid, vel=vel, dur_steps=1,
                ))

        if bar == 0:
            sid = _pick_sample(selected_samples, DrumRole.TEXTURE, 0)
            vel = velocity_for_role(DrumRole.TEXTURE, 0.2)
            grid.add_event(DrumEvent(
                bar=bar, step=0, role=DrumRole.TEXTURE,
                sample_id=sid, vel=vel, dur_steps=16,
            ))

    grid.apply_max_poly(max_poly=3)
    return grid


def display_grid(grid: EventGrid) -> str:
    lines = []
    lines.append(f"BPM: {grid.bpm} | Bars: {grid.bars} | {grid.meter}")
    lines.append("")

    def vel_char(vel: float, role: DrumRole) -> str:
        if role == DrumRole.TEXTURE:
            return "~"
        if vel >= 0.8:
            return "X"
        if vel >= 0.5:
            return "x"
        if vel >= 0.2:
            return "o"
        return "."

    for bar in range(grid.bars):
        lines.append(f"-- Bar {bar + 1} --")
        header = "        |"
        for beat in range(4):
            base_step = beat * 4
            for sub in range(4):
                if sub == 0:
                    header += f"{beat+1}"
                else:
                    header += " "
                if sub < 3:
                    header += " "
            header += "|"
        lines.append(header)

        sep = "--------+" + "-------+" * 4
        lines.append(sep)

        for role in DrumRole:
            row = f"{role.value:8s}|"
            for beat in range(4):
                for sub in range(4):
                    step = beat * 4 + sub
                    evts = [e for e in grid.events if e.bar == bar and e.step == step and e.role == role]
                    if evts:
                        ch = vel_char(evts[0].vel, role)
                    else:
                        ch = "."
                    row += f" {ch}"
                row += "|"
            lines.append(row)

        lines.append("")

    return "\n".join(lines)
