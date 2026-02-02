# Pipeline: 드럼젠-X 스테이지 오케스트레이터

## 개요

4개 스테이지를 순차 실행하는 파이프라인 러너 모음. 각 러너는 이전 스테이지의 JSON/WAV 출력을 입력으로 받아 다음 스테이지를 실행합니다.

```
원본 오디오
  ↓ run_preprocess.py
dummy_XXXXX.wav (중복 제거된 샘플)
  ↓ run_role_assignment.py
pools.json (역할별 풀)
  ↓ run_grid_and_skeleton.py
grid.json + event_grid.json + render.wav
  ↓ run_model_groovae.py
event_grid_groovae.json + render_groovae.wav
```

## 실행 순서

1. **run_preprocess.py** - 전처리 및 샘플 준비
2. **run_role_assignment.py** - 드럼 역할 할당 (DSP + CLAP)
3. **run_grid_and_skeleton.py** - 비트 그리드 및 스켈레톤 생성
4. **run_model_groovae.py** - GrooVAE 모델 기반 변형 및 렌더링

---

## Stage 1: run_preprocess.py

### 기능
원본 오디오에서 드럼 샘플을 추출하고 정리합니다.

**단계:**
1. Demucs로 혼합 오디오에서 드럼 스템 분리
2. 멀티밴드 스펙트럼 플럭스로 온셋(hit) 검출
3. 온셋 기반 개별 히트 슬라이싱
4. MFCC 기반 지문으로 유사한 샘플 중복 제거 (cosine similarity > 0.98)
5. 정규화된 WAV로 저장 (`dummy_XXXXX.wav`)

### 설정
파일 상단의 사용자 설정 변수:
```python
DATASET_ROOT = "오디오 파일 경로 (재귀 검색)"
OUTPUT_ROOT = "dummy_dataset"  # 출력 디렉터리
```

### 사용법
```bash
python pipeline/run_preprocess.py
```

### 출력
- `dummy_dataset/dummy_00001.wav` ~ `dummy_NNNNN.wav` - 중복 제거된 개별 샘플

---

## Stage 2: run_role_assignment.py

### 기능
각 샘플에 드럼 역할(CORE, ACCENT, MOTION, FILL, TEXTURE)을 할당합니다.

**역할 정의:**
| 역할 | 음악적 기능 | 특징 |
|------|-----------|------|
| CORE | 킥 계열 기초 리듬 | 저주파, 빠른 어택, 짧은 디케이 |
| ACCENT | 스네어 계열 강세 | 높은 에너지, 날카로운 트랜지언트 |
| MOTION | 하이햇 계열 유지 | 고주파, 낮은 에너지 |
| FILL | 탐 필인, 임팩트 | 높은 에너지, 긴 디케이 |
| TEXTURE | 배경/FX/앰비언스 | 긴 디케이, 부드러운 특성 |

### 스코어링 시스템
1. **DSP 기반 규칙 스코어링** - 11가지 오디오 특징(에너지, 선명도, 대역비, 어택/디케이 등)
2. **CLAP 기반 ML 스코어링** - Contrastive Language-Audio Pretraining 모델
3. **적응형 융합** - `alpha * p_rule + (1-alpha) * p_clap` (기본 alpha=0.9)
4. **가드 조건** - 부적절한 할당 억제 (예: 타격성 강한 히트는 TEXTURE 불가)

### 설정 파일
- `stage2_role_assignment/configs/role_assignment.yaml` - 모든 스코어링 가중치, 임계값, 융합 파라미터
- `stage2_role_assignment/prompts/prompts.yaml` - CLAP 텍스트 프롬프트

### 사용법
```bash
# 기본 사용 (첫 10개 파일 무작위 선택)
python pipeline/run_role_assignment.py \
  --input_dir dummy_dataset/ \
  --out_dir output/

# 전체 파일 처리
python pipeline/run_role_assignment.py \
  --input_dir dummy_dataset/ \
  --out_dir output/ \
  --limit 0

# N개 파일만 처리
python pipeline/run_role_assignment.py \
  --input_dir dummy_dataset/ \
  --out_dir output/ \
  --limit 50
```

### 출력
- `output/pools_1.json` - 역할별 샘플 풀 (형식: `{"CORE_POOL": [...], "ACCENT_POOL": [...], ...}`)
- `output/per_sample_1.json` - 각 샘플의 상세 스코어 (디버그용)

---

## Stage 3: run_grid_and_skeleton.py

### 기능
비트 그리드를 생성하고, 역할별 풀에서 샘플을 선택하여 스켈레톤 이벤트 시퀀스를 만듭니다.

### 스켈레톤 패턴
자동 생성되는 드럼 패턴:
- **CORE** - 매 마디 스텝 {0, 4, 8, 12} (four-on-the-floor)
- **ACCENT** - 백비트 스텝 {4, 12}
- **MOTION** - 하이햇 유지 (밀도 조절 가능)
- **FILL** - 4마디마다 마지막 마디의 스텝 {12, 13, 14, 15}
- **TEXTURE** - 배경음 (마디 0, 스텝 0, 지속 16스텝)
- **폴리포니 제한** - 스텝당 최대 3개 동시 발음 (우선순위: CORE > ACCENT > FILL > MOTION > TEXTURE)

### 사용법
```bash
# 기본 (BPM 120, 4마디, 랜덤 풀)
python pipeline/run_grid_and_skeleton.py \
  --out_dir output/ \
  --bpm 120

# 커스텀 설정
python pipeline/run_grid_and_skeleton.py \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --bpm 140 \
  --bars 8 \
  --seed 42 \
  --motion_mode B \
  --motion_keep 6 \
  --fill_prob 0.25 \
  --texture 1

# 샘플 경로 지정하여 오디오 렌더
python pipeline/run_grid_and_skeleton.py \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --bpm 120 \
  --sample_root dummy_dataset/
```

### 파라미터
| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `--pools_json` | "random" | 풀 JSON 경로 또는 "random" (자동 선택) |
| `--out_dir` | (필수) | 출력 디렉터리 |
| `--bpm` | (필수) | 템포 (BPM) |
| `--bars` | 4 | 마디 수 |
| `--seed` | 42 | 난수 시드 |
| `--motion_mode` | "B" | 하이햇 패턴 (A/B) |
| `--motion_keep` | 6 | 마디당 유지할 하이햇 수 (4~8) |
| `--fill_prob` | 0.25 | 필인 확률 |
| `--texture` | 1 | 배경음 포함 여부 (1/0) |
| `--sample_root` | "examples/input_samples" | 오디오 샘플 루트 (렌더링 시 필요) |
| `--render_sr` | 44100 | 렌더링 샘플링 레이트 |

### 출력
- `output/grid_N.json` - 비트 그리드 설정 (BPM, 마디, 스텝 타이밍)
- `output/event_grid_N.json` - 스켈레톤 이벤트 시퀀스
- `output/skeleton_meta_N.json` - 선택된 샘플 메타데이터
- `output/render_N.wav` - 렌더링된 오디오 (선택사항)

---

## Stage 4: run_model_groovae.py

### 기능
GrooVAE(Generative model for OOVe patterns with Variational AutoEncoder) 모델을 사용하여 드럼 패턴을 변형하고 새로운 변형을 생성합니다.

**파이프라인:**
1. 그리드 + 이벤트 → NoteSequence 변환
2. GrooVAE 모델로 변형 생성
3. 결과를 다시 이벤트로 변환
4. 선택사항: 오디오 렌더링

### 사용법
```bash
# 기본 사용
python pipeline/run_model_groovae.py \
  --grid_json output/grid_1.json \
  --events_json output/event_grid_1.json \
  --pools_json output/pools_1.json \
  --out_dir output/

# 오디오 렌더링 포함
python pipeline/run_model_groovae.py \
  --grid_json output/grid_1.json \
  --events_json output/event_grid_1.json \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --render \
  --sample_root dummy_dataset/

# 시드 지정
python pipeline/run_model_groovae.py \
  --grid_json output/grid_1.json \
  --events_json output/event_grid_1.json \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --seed 123
```

### 파라미터
| 파라미터 | 필수 | 설명 |
|---------|------|------|
| `--grid_json` | 예 | Stage 3 출력 grid_N.json |
| `--events_json` | 예 | Stage 3 출력 event_grid_N.json |
| `--pools_json` | 예 | Stage 2 출력 pools_N.json |
| `--out_dir` | 예 | 출력 디렉터리 |
| `--seed` | 아니오 | 난수 시드 (기본 42) |
| `--render` | 아니오 | 오디오 렌더링 플래그 |
| `--sample_root` | 아니오 | 샘플 루트 (렌더링 시 필요) |

### 출력
- `output/event_grid_groovae_N.json` - GrooVAE 변형된 이벤트 시퀀스
- `output/render_groovae_N.wav` - 렌더링된 오디오 (--render 사용 시)

---

## 전체 파이프라인 실행 예제

```bash
# 1단계: 전처리
python pipeline/run_preprocess.py

# 2단계: 역할 할당 (첫 10개 샘플)
python pipeline/run_role_assignment.py \
  --input_dir dummy_dataset/ \
  --out_dir output/

# 3단계: 그리드 + 스켈레톤
python pipeline/run_grid_and_skeleton.py \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --bpm 120 \
  --bars 4 \
  --sample_root dummy_dataset/

# 4단계: GrooVAE 변형
python pipeline/run_model_groovae.py \
  --grid_json output/grid_1.json \
  --events_json output/event_grid_1.json \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --render \
  --sample_root dummy_dataset/
```

---

## 데이터 흐름 상세

### 파일 형식

**pools_N.json**
```json
{
  "CORE_POOL": [
    {"sample_id": "dummy_00001", "filepath": "...", "confidence": 0.95},
    ...
  ],
  "ACCENT_POOL": [...],
  "MOTION_POOL": [...],
  "FILL_POOL": [...],
  "TEXTURE_POOL": [...],
  "counts": {"CORE": 5, "ACCENT": 3, ...}
}
```

**event_grid_N.json**
```json
[
  {
    "bar": 0,
    "step": 0,
    "role": "CORE",
    "sample_id": "dummy_00001",
    "vel": 0.9,
    "dur_steps": 4,
    "micro_offset_ms": 0.0,
    "source": "skeleton"
  },
  ...
]
```

**grid_N.json**
```json
{
  "bpm": 120,
  "meter": "4/4",
  "steps_per_bar": 16,
  "num_bars": 4,
  "tbeat": 0.5,
  "tbar": 2.0,
  "tstep": 0.125,
  "bar_start": [...],
  "t_step": [...]
}
```

---

## 문제 해결

### Stage 2에서 파일을 찾을 수 없음
```bash
# --input_dir 경로 확인
ls -la dummy_dataset/

# 전체 파일 처리하려면 --limit 0 사용
python pipeline/run_role_assignment.py \
  --input_dir dummy_dataset/ \
  --out_dir output/ \
  --limit 0
```

### Stage 3에서 오디오 렌더링 실패
```bash
# 샘플 경로가 존재하는지 확인
ls -la dummy_dataset/

# sample_root 파라미터 명시
python pipeline/run_grid_and_skeleton.py \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --bpm 120 \
  --sample_root dummy_dataset/
```

### 중복된 결과 파일
파이프라인은 자동으로 버전 번호를 부여합니다. 각 실행마다 `_1`, `_2`, `_3` 등으로 증가합니다.

---

## 기술 스택

- **오디오 처리** - librosa, soundfile, scipy
- **머신러닝** - torch, transformers (CLAP), note-seq (음악 표현)
- **외부 도구** - Demucs (음원 분리, subprocess 호출)
- **음악 이론** - custom grid/event 시스템

---

## 참고 사항

- 모든 스테이지는 **독립적으로 실행 가능**하나, 순차 실행을 권장합니다.
- GPU(CUDA)가 있으면 처리 속도가 크게 향상됩니다. CPU 폴백 지원.
- 그리드 편집은 `stage1_drumgenx/editor.py` 참고 (set, remove, velocity, render, export-midi).
