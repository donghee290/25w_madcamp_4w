# Stage 3: 비트 그리드 생성 (Beat Grid Generation)

Stage 3는 드럼 역할 할당 결과(pools)를 받아 타이밍 정보와 함께 비트 그리드를 구성하고, 역할별 스켈레톤 패턴을 생성하는 단계입니다.

## 개요

```
Stage 2 결과 (pools_json)
  ↓
grid.py → 그리드 타이밍 계산 (BPM → beat/bar/step)
  ↓
skeleton.py → 스켈레톤 패턴 생성 (역할별 규칙 기반 배치)
  ↓
events.py → Event 데이터클래스 (벨로시티, 듀레이션 매핑)
  ↓
render.py → 이벤트 믹싱 및 WAV 렌더링 (선택사항)
```

## 모듈 구조

### `grid.py` - 그리드 타이밍 계산

BPM과 박자 정보로부터 재생 타이밍을 계산합니다.

**주요 클래스:**
- `GridConfig`: 설정 데이터클래스
  - `bpm`: 분당 박자수 (beats per minute)
  - `meter_numer`, `meter_denom`: 박자 (기본 4/4)
  - `steps_per_bar`: 마디당 스텝 수 (기본 16, 16분음표 해상도)
  - `num_bars`: 총 마디 수 (기본 4)

- `GridTime`: 계산된 타이밍 정보
  - `tbeat`: 한 박 길이 (초)
  - `tbar`: 한 마디 길이 (초)
  - `tstep`: 한 스텝 길이 (초)
  - `bar_start`: 각 마디 시작 시각 (초 단위 배열)
  - `t_step`: 2D 배열 [마디][스텝] → 시각 (초)

**함수:**
```python
def build_grid(cfg: GridConfig) -> GridTime:
    """
    GridConfig로부터 GridTime을 생성합니다.
    - tbeat = 60 / bpm (한 박 길이)
    - tbar = meter_numer * tbeat (한 마디 길이)
    - tstep = tbar / steps_per_bar (한 스텝 길이)
    """
```

**예시:**
```python
cfg = GridConfig(bpm=120, num_bars=4)
grid = build_grid(cfg)
print(grid.tbar)  # 2.0 (120 BPM에서 4/4 마디는 2초)
print(grid.tstep) # 0.125 (16분음표는 0.125초)
print(grid.t_step[0][0])  # 0.0 (첫 마디 첫 스텝)
```

### `events.py` - 이벤트 데이터 및 변환

개별 드럼 이벤트를 표현하고 특징 → 음악 매개변수(벨로시티, 듀레이션) 변환을 담당합니다.

**주요 클래스:**
- `Event`: 개별 드럼 타격 정보
  - `bar`: 마디 인덱스 (0~num_bars-1)
  - `step`: 마디 내 스텝 (0~15)
  - `role`: 드럼 역할 ("CORE" | "ACCENT" | "MOTION" | "FILL" | "TEXTURE")
  - `sample_id`: 사용할 원샷 샘플 ID
  - `vel`: 벨로시티 (0.0~1.0)
  - `dur_steps`: 이벤트 지속 시간 (스텝 단위)
  - `micro_offset_ms`: 미시적 타이밍 오프셋 (기본 0.0)
  - `source`: 출처 ("skeleton" | "groove" | "user_edit" 등)

**주요 함수:**

- `vel_from_energy(role: str, energy: float) -> float`

  에너지 특징값 → 벨로시티 매핑 (역할별 서로 다른 곡선):
  - `CORE`: 0.60 + 0.40 * energy
  - `ACCENT`: 0.70 + 0.30 * energy
  - `MOTION`: 0.25 + 0.35 * energy
  - `FILL`: 0.75 + 0.25 * energy
  - `TEXTURE`: 0.15~0.35 (랜덤)

- `dur_from_decay(decay_sec: float, tstep: float, role: str) -> int`

  디케이 특징값 → 듀레이션 매핑:
  - `TEXTURE`: 항상 16 스텝 (마디 전체)
  - 기타 역할: 디케이가 tstep * 0.95보다 길면 2 스텝, 아니면 1 스텝

### `patterns/skeleton.py` - 스켈레톤 패턴 생성

역할별 규칙 기반 드럼 패턴을 생성합니다.

**주요 클래스:**
- `SkeletonConfig`: 패턴 생성 설정
  - `seed`: 난수 생성 시드 (기본 42)
  - `steps_per_bar`: 마디당 스텝 (기본 16)
  - `num_bars`: 총 마디 (기본 4)
  - `motion_mode`: 하이햇 밀도 ("A" | "B", 기본 "A")
  - `motion_keep_per_bar`: 마디당 하이햇 개수 (기본 6)
  - `fill_every_n_bars`: 필인 빈도 (기본 매 4 마디)
  - `fill_prob`: 필인 확률 (기본 0.25)
  - `texture_enabled`: 배경음 포함 여부 (기본 True)
  - `max_poly`: 동시 발음 최대값 (기본 3)

**함수:**
```python
def build_skeleton_events(
    pools_json: Dict[str, List[dict]],
    cfg: SkeletonConfig,
    tstep: float = 0.125,
) -> Tuple[List[Event], Dict[str, str]]:
    """
    역할별 풀에서 샘플을 선택하고 스켈레톤 패턴을 생성합니다.

    pools_json 구조:
    {
        "CORE_POOL": [{"sample_id": "...", "features": {...}}, ...],
        "ACCENT_POOL": [...],
        "MOTION_POOL": [...],
        "FILL_POOL": [...],
        "TEXTURE_POOL": [...]
    }

    반환값:
    - events: 생성된 Event 리스트
    - chosen: {"CORE": "sample_id", "ACCENT": "sample_id", ...}
    """
```

**스켈레톤 패턴 규칙:**

| 역할 | 배치 규칙 | 스텝 | 설명 |
|------|---------|------|------|
| **CORE** | Four-on-the-floor | 0, 4, 8, 12 | 모든 마디에서 고정 배치 |
| **ACCENT** | 백비트 | 4, 12 | 모든 마디에서 고정 배치 |
| **MOTION** | 밀도 기반 | A 셋: 2, 6, 10, 14 / B 셋: 1, 3, 5, 7, 9, 11, 13, 15 | 마디당 motion_keep_per_bar개만 선택 |
| **FILL** | 필인 | 12, 13, 14, 15 | 마지막 마디에서 fill_prob 확률로 1~3개 스텝 |
| **TEXTURE** | 지속음 | 0 (dur=16) | 모든 마디 시작 (마디 전체 지속) |

**동시 발음 제한:**
- 같은 (bar, step)에 최대 max_poly개 이벤트만 허용
- 삭제 우선순위: TEXTURE(낮음) > MOTION > ACCENT/FILL > CORE(높음)

### `test_audio_render/render.py` - 오디오 렌더링

Event 리스트와 샘플을 믹싱하여 최종 WAV 파일을 생성합니다.

**함수:**

- `load_wav_mono(path: Path, target_sr: int) -> np.ndarray`

  단일 WAV 파일을 로드하고 모노 리샘플링합니다.

- `apply_fade(y: np.ndarray, fade_ms: float, sr: int) -> np.ndarray`

  페이드-인/아웃을 적용하여 클릭음을 제거합니다.

- `render_events(grid_json, events, sample_root, out_wav, target_sr=44100, master_gain=0.9)`

  이벤트를 믹싱하여 WAV로 렌더링합니다.
  - 각 이벤트의 타이밍, 벨로시티, 듀레이션 적용
  - 동적 범위 정규화 (클리핑 방지)
  - 마스터 게인 적용

## 사용 예제

### 1. 그리드 생성

```python
from stage3_beat_grid.grid import GridConfig, build_grid

# 120 BPM, 4 마디
cfg = GridConfig(bpm=120, num_bars=4)
grid = build_grid(cfg)

print(f"마디당 길이: {grid.tbar}초")
print(f"스텝당 길이: {grid.tstep}초")
```

### 2. 스켈레톤 패턴 생성

```python
import json
from stage3_beat_grid.patterns.skeleton import SkeletonConfig, build_skeleton_events

# pools.json 로드
with open("pools.json") as f:
    pools = json.load(f)

# 패턴 설정
cfg = SkeletonConfig(bpm=120, num_bars=4, motion_mode="A")

# 패턴 생성
events, chosen = build_skeleton_events(pools, cfg, tstep=0.125)

print(f"생성된 이벤트 수: {len(events)}")
print(f"선택 샘플: {chosen}")

# 이벤트 출력
for e in events[:5]:
    print(f"  {e.bar}:{e.step} {e.role} vel={e.vel:.2f}")
```

### 3. 오디오 렌더링 (선택사항)

```python
import json
from pathlib import Path
from stage3_beat_grid.test_audio_render.render import render_events

# 그리드 정보
grid_json = {
    "num_bars": 4,
    "tbar": 2.0,
    "tstep": 0.125
}

# 이벤트를 딕셔너리로 변환
events_dict = [
    {
        "bar": e.bar,
        "step": e.step,
        "role": e.role,
        "sample_id": e.sample_id,
        "vel": e.vel,
        "dur_steps": e.dur_steps,
        "micro_offset_ms": e.micro_offset_ms,
    }
    for e in events
]

# 렌더링
render_events(
    grid_json=grid_json,
    events=events_dict,
    sample_root=Path("samples/"),
    out_wav=Path("output.wav"),
    target_sr=44100,
    master_gain=0.9,
)
```

## CLI 통합

Stage 1 메인 파이프라인에서 Stage 3를 호출하는 예:

```bash
# 전체 파이프라인 (Stage 1 + 2 + 3)
python -m stage1_drumgenx pipeline --n-files 5

# 수동으로 그리드 + 패턴 생성
python -m stage1_drumgenx generate output.json --bpm 120 --bars 4

# 패턴 시각화 (ASCII)
python -m stage1_drumgenx show output.json

# 최종 오디오 렌더링
python -m stage1_drumgenx render output.json --output out.wav --reverb
```

## 주요 특징

### 시드 기반 재현성
SkeletonConfig에서 seed를 고정하면 동일한 난수 시퀀스로 항상 같은 패턴을 생성합니다.

### 특징 기반 벨로시티/듀레이션
각 샘플의 에너지, 디케이 특징을 역할별 매핑 함수로 음악 매개변수로 변환합니다.

### 폴리포니 제어
동시 발음을 제한하여 음악적으로 자연스러운 배치를 보장합니다.

### 역할별 독립 선택
각 역할에서 하나의 샘플을 선택하므로 (MOTION 제외), 역할 간 혼합이 명확합니다.

## 데이터 포맷

### pools.json
Stage 2에서 생성되는 역할별 샘플 풀:

```json
{
  "CORE_POOL": [
    {
      "sample_id": "kick_001",
      "filepath": "/path/to/kick_001.wav",
      "features": {
        "energy": 0.85,
        "decay_time": 0.15,
        "sharpness": 0.3
      }
    }
  ],
  "ACCENT_POOL": [...],
  "MOTION_POOL": [...],
  "FILL_POOL": [...],
  "TEXTURE_POOL": [...]
}
```

### Event JSON
렌더링용 이벤트 리스트:

```json
[
  {
    "bar": 0,
    "step": 0,
    "role": "CORE",
    "sample_id": "kick_001",
    "vel": 0.8,
    "dur_steps": 1,
    "micro_offset_ms": 0.0,
    "source": "skeleton"
  },
  ...
]
```

## 트러블슈팅

### "sample not found" 경고
- 샘플 경로가 sample_root 디렉토리 안에 있는지 확인
- Event에 filepath를 직접 포함하면 우선적으로 사용됨

### 렌더링이 조용함
- master_gain 값을 높입니다 (기본 0.9 → 1.0 시도)
- 벨로시티 매핑 함수를 검토합니다 (vel_from_energy)
- 원샷 샘플이 적절한 에너지를 갖는지 확인

### 패턴이 반복되지 않음
- SkeletonConfig의 seed를 고정합니다 (기본 42)
- 난수 생성기가 같은 seed로 초기화되어야 합니다

## 관련 문서

- [Stage 1: 드럼 추출 및 분류](../stage1_drumgenx/README.md)
- [Stage 2: 역할 할당](../stage2_role_assignment/README.md)
- [Stage 4: 모델 생성](../stage4_model_gen/README.md)
