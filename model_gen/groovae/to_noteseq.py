# model_gen/groovae/to_noteseq.py
from __future__ import annotations

from typing import Dict, List
from note_seq.protobuf import music_pb2

from model_gen.groovae.mapping import ROLE_TO_PITCHES


def events_to_notesequence(
    grid_json: Dict,
    events: List[Dict],
) -> music_pb2.NoteSequence:

    ns = music_pb2.NoteSequence()
    ns.tempos.add(qpm=grid_json["bpm"])
    ns.time_signatures.add(
        numerator=4,
        denominator=4
    )

    Tstep = grid_json["tstep"]

    for e in events:
        role = e["role"]
        if role == "TEXTURE":
            continue

        pitches = ROLE_TO_PITCHES.get(role)
        if not pitches:
            continue

        pitch = pitches[e["bar"] % len(pitches)]

        start = (
            e["bar"] * grid_json["tbar"]
            + e["step"] * Tstep
            + (e.get("micro_offset_ms", 0.0) / 1000.0)
        )
        dur = e["dur_steps"] * Tstep
        end = start + dur

        vel = int(round(1 + 126 * e["vel"]))

        note = ns.notes.add()
        note.pitch = pitch
        note.velocity = vel
        note.start_time = max(0.0, start)
        note.end_time = max(note.start_time + 1e-4, end)
        note.is_drum = True

    ns.total_time = max(
        (n.end_time for n in ns.notes), default=0.0
    )
    return ns