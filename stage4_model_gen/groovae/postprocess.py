# model_gen/groovae/postprocess.py
from __future__ import annotations

from typing import Dict, List
from note_seq.protobuf import music_pb2

from stage4_model_gen.groovae.mapping import PITCH_TO_ROLE


def quantize_and_filter(
    ns: music_pb2.NoteSequence,
    grid_json: Dict,
    max_poly: int = 3,
) -> music_pb2.NoteSequence:

    Tstep = grid_json["tstep"]
    Tbar = grid_json["tbar"]

    buckets = {}

    for note in ns.notes:
        bar = int(note.start_time // Tbar)
        step = int(round((note.start_time - bar * Tbar) / Tstep))
        step = max(0, min(15, step))

        key = (bar, step)
        buckets.setdefault(key, []).append(note)

    new_ns = music_pb2.NoteSequence()
    new_ns.tempos.extend(ns.tempos)
    new_ns.time_signatures.extend(ns.time_signatures)

    for (bar, step), notes in buckets.items():
        notes_sorted = sorted(
            notes,
            key=lambda n: (
                0 if PITCH_TO_ROLE.get(n.pitch) == "CORE" else
                1 if PITCH_TO_ROLE.get(n.pitch) == "ACCENT" else
                2
            )
        )

        kept = notes_sorted[:max_poly]

        for n in kept:
            new_note = new_ns.notes.add()
            new_note.CopyFrom(n)

    new_ns.total_time = max(
        (n.end_time for n in new_ns.notes), default=0.0
    )
    return new_ns