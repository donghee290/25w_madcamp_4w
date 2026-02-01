# model_gen/groovae/mapping.py
from __future__ import annotations

# GM Drum Map (대표 pitch)
ROLE_TO_PITCHES = {
    "CORE": [36],              # Kick
    "ACCENT": [38],            # Snare
    "MOTION": [42, 44],        # Closed HH, Pedal HH
    "FILL": [45, 47, 48],      # Low / Mid / High Tom
}

PITCH_TO_ROLE = {}
for role, pitches in ROLE_TO_PITCHES.items():
    for p in pitches:
        PITCH_TO_ROLE[p] = role