# 25w_madcamp_4w (DrumGen-X)

환경음/음악 오디오에서 드럼 히트를 추출하고, 역할을 부여한 뒤 비트 그리드와 스켈레톤 패턴을 생성하며, GrooVAE 기반 변형까지 연결하는 4-스테이지 파이프라인입니다.

## 구성

- `pipeline/`: 전체 스테이지 실행 스크립트
- `stage1_drumgenx/`: DSP 전처리, 킷 빌드, 스켈레톤/렌더
- `stage2_role_assignment/`: DSP + CLAP 역할 할당
- `stage3_beat_grid/`: 그리드/스켈레톤 이벤트 생성
- `stage4_model_gen/`: note-seq 변환 + GrooVAE 변형
- `sample_input/`: 예제 오디오/킷
- `README_PREPROCESS.md`: 전처리 러너(standalone) 설명
- `requirements.txt`: 의존성 목록

## 설치

```bash
pip install -r requirements.txt
```

## 빠른 시작 (End-to-End)

### 1) 입력 오디오 준비

- 여러 파일을 일괄 처리하려면 `pipeline/run_preprocess.py` 상단의 `DATASET_ROOT`를 실제 오디오 폴더 경로로 수정하세요.
- 단일 파일 기반 전처리는 `README_PREPROCESS.md`를 참고하세요.

### 2) Stage 1: 전처리

```bash
python pipeline/run_preprocess.py
```

출력: `dummy_dataset/dummy_*.wav`

### 3) Stage 2: 역할 할당

```bash
python pipeline/run_role_assignment.py \
  --input_dir dummy_dataset/ \
  --out_dir output/
```

출력: `output/pools_*.json`

### 4) Stage 3: 비트 그리드/스켈레톤

```bash
python pipeline/run_grid_and_skeleton.py \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --bpm 120 \
  --sample_root dummy_dataset/
```

출력: `output/grid_*.json`, `output/event_grid_*.json`, `output/render_*.wav` (옵션)

### 5) Stage 4: GrooVAE 변형

```bash
python pipeline/run_model_groovae.py \
  --grid_json output/grid_1.json \
  --events_json output/event_grid_1.json \
  --pools_json output/pools_1.json \
  --out_dir output/ \
  --render \
  --sample_root dummy_dataset/
```

출력: `output/event_grid_groovae_*.json`, `output/render_groovae_*.wav`

## 스테이지 문서

- Stage 1: `stage1_drumgenx/README.md`
- Stage 2: `stage2_role_assignment/README.md`
- Stage 3: `stage3_beat_grid/README.md`
- Stage 4: `stage4_model_gen/README.md`
- 파이프라인 러너: `pipeline/README.md`
- 전처리 러너: `README_PREPROCESS.md`

## 참고

- CLAP 모델은 첫 실행 시 다운로드됩니다.
- GPU 사용 시 속도가 크게 향상됩니다. CPU 폴백도 지원합니다.
- 출력 파일은 실행마다 `_1`, `_2` 등 버전이 증가합니다.
