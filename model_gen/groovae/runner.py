# model_gen/groovae/runner.py
from __future__ import annotations

from note_seq.protobuf import music_pb2


class GrooVAERunner:
    """
    MVP용 더미 runner
    (GrooVAE 연결 시 이 클래스만 교체)
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def run(self, ns: music_pb2.NoteSequence) -> music_pb2.NoteSequence:
        # 현재는 그대로 반환 (인터페이스 고정용)
        return ns