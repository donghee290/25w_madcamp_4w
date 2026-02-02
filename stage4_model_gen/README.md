# Stage 4: GrooVAE 생성 모델 통합

## 개요

Stage 3에서 생성된 스켈레톤 패턴(EventGrid)을 GrooVAE(Groove Variational Autoencoder)에 입력하여 인간적인 그루브, 마이크로타이밍, 벨로시티 변화가 적용된 드럼 시퀀스를 생성합니다.

Google Magenta의 `note-seq` 라이브러리를 활용하여 Event 포맷과 MIDI NoteSequence 간 양방향 변환을 수행합니다.

## 데이터 흐름

```
Stage 3 EventGrid (JSON)
    ↓
to_noteseq.py
    ├─ Event → music_pb2.NoteSequence
    └─ 역할별 GM 드럼 맵 적용
    ↓
runner.py (GrooVAE 추론)
    ├─ 현재: placeholder (그대로 반환)
    └─ 향후: 실제 모델 통합 자리
    ↓
postprocess.py (후처리)
    ├─ 그리드 양자화 (오프셋 제거)
    └─ 최대 폴리포니 제한 (3음)
    ↓
from_noteseq.py
    ├─ NoteSequence → Event
    └─ 라운드 로빈 샘플 선택
    ↓
최종 Event 리스트 (마이크로타이밍 적용)
```

## 아키텍처

### groovae/ 모듈 구조

```
groovae/
├── __init__.py          # 패키지 초기화
├── mapping.py           # GM 드럼 맵 (역할↔MIDI pitch)
├── to_noteseq.py        # Event → NoteSequence 변환
├── from_noteseq.py      # NoteSequence → Event 변환
├── postprocess.py       # 양자화 및 폴리포니 필터링
└── runner.py            # GrooVAE 추론 러너 (MVP)
```

## 모듈 상세 설명

### mapping.py

**목적**: Event의 `role` 필드와 MIDI pitch 간 매핑

```python
ROLE_TO_PITCHES = {
    "CORE": [36],           # 킥 (Bass Drum)
    "ACCENT": [38],         # 스네어 (Snare)
    "MOTION": [42, 44],     # 하이햇 (Closed HH, Pedal HH)
    "FILL": [45, 47, 48],   # 탐 (Low / Mid / High Tom)
}

PITCH_TO_ROLE = {
    36: "CORE", 38: "ACCENT",
    42: "MOTION", 44: "MOTION",
    45: "FILL", 47: "FILL", 48: "FILL",
}
```

**주의**: TEXTURE 역할은 NoteSequence에 매핑되지 않음 (앰비언스/지속음이므로 스킵)

---

### to_noteseq.py

**함수**: `events_to_notesequence(grid_json, events) → music_pb2.NoteSequence`

**역할**: Event 리스트를 note-seq NoteSequence 포맷으로 변환

**변환 로직**:
1. 각 Event에서 `role`을 역할별 pitch 목록에 매핑
2. `bar` 인덱스로 라운드 로빈 선택 (역할 다양성 보장)
3. 타이밍 계산:
   - `start = bar * tbar + step * tstep + micro_offset_ms / 1000`
   - `duration = dur_steps * tstep`
4. Velocity 정규화: `vel_midi = 1 + round(126 * vel)` (0~127 범위)

**입력**:
- `grid_json`: BPM, tstep (스텝 간격), tbar (마디 간격) 포함
- `events`: Event dict 리스트

**출력**:
- MIDI NoteSequence (tempo, time_signature, notes 포함)

---

### runner.py

**클래스**: `GrooVAERunner`

**현재 상태**: MVP용 더미 구현 (그대로 반환)

```python
class GrooVAERunner:
    def __init__(self, seed: int = 42):
        self.seed = seed

    def run(self, ns: music_pb2.NoteSequence) -> music_pb2.NoteSequence:
        # 향후 GrooVAE 모델 추론 로직 추가
        return ns
```

**인터페이스 고정**: 실제 모델 통합 시 이 클래스 내부만 교체

---

### postprocess.py

**함수**: `quantize_and_filter(ns, grid_json, max_poly=3) → music_pb2.NoteSequence`

**역할**: GrooVAE 추론 결과 정제

**처리 순서**:
1. **그리드 양자화**: 모든 note를 가장 가까운 그리드 위치로 스냅
   - bar, step 계산: `step = round((start_time - bar * tbar) / tstep)`
   - step 범위 제한: `[0, 15]` (16분음표 기준)

2. **최대 폴리포니 필터링**:
   - 각 (bar, step)에 여러 note가 들어올 경우, 역할 우선순위로 정렬
   - 우선순위: CORE > ACCENT > FILL > 기타
   - 상위 `max_poly`개만 유지 (기본값 3)

**입력**:
- `ns`: GrooVAERunner.run() 출력
- `grid_json`: 그리드 설정
- `max_poly`: 스텝당 최대 동시 음수 (기본 3)

**출력**:
- 정제된 NoteSequence

---

### from_noteseq.py

**함수**: `noteseq_to_events(ns, grid_json, sample_map) → List[Dict]`

**역할**: NoteSequence를 다시 Event 포맷으로 변환 (라운드 로빈 샘플 할당)

**변환 로직**:
1. 각 MIDI note에서:
   - pitch → role 매핑
   - start_time → (bar, step) 계산
   - velocity → normalized [0, 1]

2. **라운드 로빈 샘플 선택**:
   ```python
   rr_idx = {k: 0 for k in sample_map}  # 역할별 인덱스
   sample = sample_map[role][rr_idx[role] % len(sample_map[role])]
   rr_idx[role] += 1
   ```
   - 같은 역할의 Event 여러 개는 다른 샘플로 할당
   - 예: CORE 3개 → kick1, kick2, kick3 순차 선택

3. **마이크로타이밍 보존**:
   ```python
   micro_offset_ms = (note.start_time - (bar * tbar + step * tstep)) * 1000
   ```

**입력**:
- `ns`: postprocess 결과
- `grid_json`: 그리드 설정
- `sample_map`: `{"CORE": [...], "ACCENT": [...], ...}`

**출력**:
- Event dict 리스트 (source="groovae" 마크)

---

## 사용 예시

### 최소 예제

```python
from stage4_model_gen.groovae import (
    to_noteseq,
    runner,
    postprocess,
    from_noteseq,
)

# 1. Event → NoteSequence
events = [
    {"bar": 0, "step": 0, "role": "CORE", "vel": 0.9, "dur_steps": 1},
    {"bar": 0, "step": 4, "role": "ACCENT", "vel": 0.8, "dur_steps": 1},
]
grid_json = {"bpm": 120, "tstep": 0.0625, "tbar": 1.0}

ns = to_noteseq.events_to_notesequence(grid_json, events)

# 2. GrooVAE 추론 (현재: dummy)
runner_obj = runner.GrooVAERunner(seed=42)
ns_grooved = runner_obj.run(ns)

# 3. 후처리 (양자화 + 폴리포니)
ns_clean = postprocess.quantize_and_filter(ns_grooved, grid_json, max_poly=3)

# 4. NoteSequence → Event
sample_map = {
    "CORE": [{"sample_id": "k1", "filepath": "..."}],
    "ACCENT": [{"sample_id": "s1", "filepath": "..."}],
}
final_events = from_noteseq.noteseq_to_events(ns_clean, grid_json, sample_map)
```

### CLI 통합 (run_model_groovae.py)

```bash
python -m stage1_drumgenx pipeline --n-files 5
# ... 완료 후 stage4_model_gen 자동 호출
```

---

## 핵심 설정값

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `BPM` | 120 | 드럼 루프 템포 (stage3에서 설정) |
| `grid_resolution` | 16 | 한 마디 내 스텝 수 (16분음표) |
| `tstep` | 1/16 beat | 스텝 간격 (초 단위) |
| `tbar` | 1.0 beat | 마디 간격 (초 단위, 4/4 기준) |
| `max_polyphony` | 3 | postprocess에서 스텝당 최대 음수 |

---

## 데이터 포맷

### Event Dict

```json
{
    "bar": 0,
    "step": 4,
    "role": "ACCENT",
    "sample_id": "snare_001",
    "filepath": "/path/to/snare.wav",
    "vel": 0.85,
    "dur_steps": 1,
    "micro_offset_ms": -2.5,
    "source": "groovae"
}
```

### NoteSequence (protobuf)

```
NoteSequence:
  tempos: [qpm=120]
  time_signatures: [numerator=4, denominator=4]
  notes:
    - pitch=36, velocity=127, start_time=0.0, end_time=0.0625
    - pitch=38, velocity=107, start_time=0.25, end_time=0.3125
    ...
```

---

## 확장 포인트

### GrooVAE 모델 통합

`runner.py`의 `GrooVAERunner.run()` 메서드만 교체:

```python
def run(self, ns: music_pb2.NoteSequence) -> music_pb2.NoteSequence:
    # 1. NoteSequence → 모델 입력 (e.g., 피아노 롤)
    # 2. 모델 추론 (forward pass)
    # 3. 출력 → NoteSequence
    return ns_grooved
```

### 사용자 정의 드럼 맵

`mapping.py`의 `ROLE_TO_PITCHES` 확장:

```python
ROLE_TO_PITCHES = {
    "CORE": [36, 35],      # 추가 대체 pitch
    "ACCENT": [38, 37],
    ...
}
```

---

## 성능 및 제약

- **NoteSequence 변환**: O(n) (이벤트 수에 선형)
- **postprocess 양자화**: O(n log n) (정렬 포함)
- **메모리**: 시퀀스 길이에 비례 (수 MB 미만, 일반적)
- **마이크로타이밍 정밀도**: ±1ms (float 반올림)

---

## 테스트 및 검증

### 라운드 트립 검증

Event → NoteSequence → Event 변환 시 정보 손실 확인:

```python
events_orig = [...]
ns = to_noteseq.events_to_notesequence(grid_json, events_orig)
ns_clean = postprocess.quantize_and_filter(ns, grid_json)
events_recovered = from_noteseq.noteseq_to_events(ns_clean, grid_json, sample_map)

# 검증: bar, step, role 일치 확인
assert events_orig[0]["bar"] == events_recovered[0]["bar"]
```

**주의**: velocity, sample_id는 양자화로 인해 변경될 수 있음

---

## 의존성

```
note-seq       # protobuf NoteSequence 포맷
numpy          # 행렬 연산
torch          # 향후 모델 추론용
```

설치:
```bash
pip install note-seq torch
```

---

## 상태 및 로드맵

| 항목 | 상태 | 참고 |
|------|------|------|
| Event ↔ NoteSequence 변환 | 완료 | to_noteseq.py, from_noteseq.py |
| 양자화 + 폴리포니 필터 | 완료 | postprocess.py |
| 라운드 로빈 샘플 할당 | 완료 | from_noteseq.py |
| GrooVAE 모델 추론 | Placeholder | runner.py |
| 마이크로타이밍 보존 | 완료 | micro_offset_ms 필드 |

**다음 단계**: 실제 GrooVAE 또는 대체 생성 모델 통합

---

## 기여 및 문의

Stage 4는 Stage 3 (beat-grid)의 후속 스테이지입니다.
이전 단계 또는 Stage 2 (role-assignment)와 연계된 이슈는 각 패키지 README를 참고하세요.
