"""GrooVAE-based humanization for drum sequences."""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from .scoring import DrumRole

logger = logging.getLogger("drumgenx")

# MIDI note mapping (General MIDI drum standard)
ROLE_TO_MIDI = {
    DrumRole.CORE: 36,      # Kick / Bass Drum 1
    DrumRole.ACCENT: 38,    # Snare / Acoustic Snare
    DrumRole.MOTION: 42,    # HiHat Closed
    DrumRole.FILL: 45,      # Tom Low
    # TEXTURE excluded from GrooVAE
}

MIDI_TO_ROLE = {v: k for k, v in ROLE_TO_MIDI.items()}

# Lazy-loaded model
_groovae_model = None
_groovae_config = None


def _load_groovae(checkpoint_path: Optional[str] = None):
    """Lazy-load GrooVAE model.

    Requires magenta and note-seq installed.
    """
    global _groovae_model, _groovae_config
    if _groovae_model is not None:
        return _groovae_model

    try:
        import note_seq
        from magenta.models.music_vae import configs as vae_configs
        from magenta.models.music_vae.trained_model import TrainedModel
    except ImportError:
        raise ImportError(
            "GrooVAE requires magenta and note-seq. "
            "Install with: pip install magenta note-seq"
        )

    config_name = "groovae_4bar"
    _groovae_config = vae_configs.CONFIG_MAP[config_name]

    if checkpoint_path is None:
        # Use default magenta checkpoint
        logger.warning("No GrooVAE checkpoint specified. "
                       "Download from: https://storage.googleapis.com/magentadata/models/music_vae/checkpoints/")
        raise FileNotFoundError("GrooVAE checkpoint path required. Set via config.")

    logger.info(f"Loading GrooVAE from {checkpoint_path}...")
    _groovae_model = TrainedModel(
        _groovae_config,
        batch_size=1,
        checkpoint_dir_or_path=checkpoint_path,
    )
    logger.info("GrooVAE loaded successfully")
    return _groovae_model


def events_to_note_sequence(events, grid):
    """Convert EventGrid events to a NoteSequence for GrooVAE.

    Args:
        events: List of DrumEvent from events.py
        grid: EventGrid containing timing info

    Returns:
        note_seq.NoteSequence
    """
    import note_seq

    ns = note_seq.NoteSequence()
    ns.tempos.add(qpm=grid.bpm)

    for event in events:
        # Skip TEXTURE (not processed by GrooVAE)
        if event.role == DrumRole.TEXTURE:
            continue

        midi_note = ROLE_TO_MIDI.get(event.role)
        if midi_note is None:
            continue

        # Calculate time
        t_start = grid.event_time(event)
        t_end = t_start + grid.t_step * event.dur_steps

        # Convert velocity to MIDI (1-127)
        vel_midi = max(1, min(127, int(round(1 + 126 * event.vel))))

        note = ns.notes.add()
        note.pitch = midi_note
        note.start_time = t_start
        note.end_time = t_end
        note.velocity = vel_midi
        note.is_drum = True
        note.instrument = 9  # GM drum channel

    # Set total time
    if ns.notes:
        ns.total_time = max(n.end_time for n in ns.notes)
    else:
        ns.total_time = grid.bars * grid.t_bar

    return ns


def note_sequence_to_events(ns, grid, selected_samples=None):
    """Convert GrooVAE output NoteSequence back to DrumEvents.

    Args:
        ns: note_seq.NoteSequence from GrooVAE
        grid: EventGrid with timing parameters
        selected_samples: Dict[DrumRole, List[str]] for sample_id assignment

    Returns:
        List of DrumEvent
    """
    from .events import DrumEvent

    events = []
    motion_idx = 0

    for note in ns.notes:
        if not note.is_drum:
            continue

        role = MIDI_TO_ROLE.get(note.pitch)
        if role is None:
            continue

        # Quantize to nearest grid step
        t = note.start_time
        bar = int(t / grid.t_bar)
        remainder = t - bar * grid.t_bar
        step = int(round(remainder / grid.t_step))

        # Clamp to valid range
        bar = max(0, min(bar, grid.bars - 1))
        step = max(0, min(step, grid.resolution - 1))

        # Calculate micro_offset (deviation from perfect grid)
        perfect_time = bar * grid.t_bar + step * grid.t_step
        micro_offset_ms = (t - perfect_time) * 1000.0
        # Clamp micro offset to ±50ms
        micro_offset_ms = max(-50.0, min(50.0, micro_offset_ms))

        # Velocity back to 0-1
        vel = (note.velocity - 1) / 126.0

        # Sample ID assignment
        if selected_samples and role in selected_samples:
            pool = selected_samples[role]
            if pool:
                if role == DrumRole.MOTION:
                    sample_id = pool[motion_idx % len(pool)]
                    motion_idx += 1
                else:
                    sample_id = pool[0]
            else:
                sample_id = f"{role.value}_default"
        else:
            sample_id = f"{role.value}_default"

        events.append(DrumEvent(
            bar=bar,
            step=step,
            role=role,
            sample_id=sample_id,
            vel=vel,
            dur_steps=1,
            micro_offset_ms=micro_offset_ms,
        ))

    return events


def humanize_grid(
    grid,
    checkpoint_path: Optional[str] = None,
    temperature: float = 0.5,
    selected_samples: Optional[Dict[DrumRole, list]] = None,
):
    """Apply GrooVAE humanization to an EventGrid.

    Args:
        grid: EventGrid to humanize
        checkpoint_path: Path to GrooVAE checkpoint
        temperature: Sampling temperature (higher = more variation)
        selected_samples: Sample pool for re-assignment

    Returns:
        New EventGrid with humanized timing and velocities
    """
    from .events import EventGrid as EG, DrumEvent

    model = _load_groovae(checkpoint_path)

    # Convert to NoteSequence
    ns = events_to_note_sequence(grid.events, grid)

    # Run GrooVAE encode-decode
    import note_seq

    # Quantize input for GrooVAE
    qns = note_seq.quantize_note_sequence(ns, steps_per_quarter=4)

    # Encode
    z, _, _ = model.encode([qns])

    # Decode with temperature
    decoded = model.decode(
        z=z,
        length=grid.bars * grid.resolution,
        temperature=temperature,
    )

    if not decoded:
        logger.warning("GrooVAE produced no output, returning original grid")
        return grid

    decoded_ns = decoded[0]

    # Convert back to events
    humanized_events = note_sequence_to_events(
        decoded_ns, grid, selected_samples
    )

    # Preserve TEXTURE events from original (GrooVAE doesn't handle them)
    texture_events = [e for e in grid.events if e.role == DrumRole.TEXTURE]
    humanized_events.extend(texture_events)

    # Protect CORE and ACCENT on skeleton positions
    # Ensure CORE on {0,4,8,12} and ACCENT on {4,12} are not removed
    skeleton_core = {(e.bar, e.step) for e in humanized_events
                     if e.role == DrumRole.CORE and e.step in {0, 4, 8, 12}}
    skeleton_accent = {(e.bar, e.step) for e in humanized_events
                       if e.role == DrumRole.ACCENT and e.step in {4, 12}}

    # If any skeleton position is missing, restore from original
    for bar in range(grid.bars):
        for step in [0, 4, 8, 12]:
            if (bar, step) not in skeleton_core:
                orig = [e for e in grid.events
                        if e.bar == bar and e.step == step and e.role == DrumRole.CORE]
                if orig:
                    humanized_events.append(orig[0])

        for step in [4, 12]:
            if (bar, step) not in skeleton_accent:
                orig = [e for e in grid.events
                        if e.bar == bar and e.step == step and e.role == DrumRole.ACCENT]
                if orig:
                    humanized_events.append(orig[0])

    # Build new grid
    new_grid = EG(
        bpm=grid.bpm,
        meter=grid.meter,
        resolution=grid.resolution,
        bars=grid.bars,
        events=humanized_events,
        kit_dir=grid.kit_dir,
    )

    # Apply max polyphony
    new_grid.apply_max_poly(max_poly=3)

    return new_grid


def simple_humanize(grid, amount: float = 0.3, seed: int = 42):
    """Simple micro-timing humanization without GrooVAE.

    Adds small random offsets to event timing for a more natural feel.
    Use this as fallback when GrooVAE is not available.

    Args:
        grid: EventGrid to humanize
        amount: Maximum offset in milliseconds (default 0.3 = ±15ms)
        seed: Random seed for reproducibility

    Returns:
        New EventGrid with micro-timing offsets
    """
    import random as _random
    from .events import EventGrid as EG, DrumEvent

    rng = _random.Random(seed)

    new_events = []
    for event in grid.events:
        # Don't humanize TEXTURE (sustained pads)
        if event.role == DrumRole.TEXTURE:
            new_events.append(event)
            continue

        # Random micro offset in ms
        max_ms = amount * 50.0  # amount=1.0 → ±50ms
        offset = rng.uniform(-max_ms, max_ms)

        # Vary velocity slightly
        vel_var = rng.uniform(-0.05, 0.05) * amount
        new_vel = max(0.05, min(1.0, event.vel + vel_var))

        new_events.append(DrumEvent(
            bar=event.bar,
            step=event.step,
            role=event.role,
            sample_id=event.sample_id,
            vel=round(new_vel, 3),
            dur_steps=event.dur_steps,
            micro_offset_ms=round(offset, 2),
        ))

    return EG(
        bpm=grid.bpm,
        meter=grid.meter,
        resolution=grid.resolution,
        bars=grid.bars,
        events=new_events,
        kit_dir=grid.kit_dir,
    )
