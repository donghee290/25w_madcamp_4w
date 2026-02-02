# Stage 1: 핵심 전처리 파이프라인

## 개요

Stage 1은 드럼 킷 생성을 위한 핵심 DSP 전처리 파이프라인입니다. Demucs로 원본 오디오에서 드럼 스템을 분리하고, 멀티밴드 스펙트럼 플럭스 기반 온셋 검출로 개별 타격음을 찾은 후, 슬라이싱 및 MFCC+DSP 기반 중복 제거를 통해 의미 있는 샘플들을 추출합니다. 이후 규칙 기반 스코어링으로 각 샘플을 5가지 드럼 역할(CORE/ACCENT/MOTION/FILL/TEXTURE)로 분류하고, 풀 밸런싱으로 역할별 최소 샘플 수를 보장한 뒤, 그리드 기반 스켈레톤 패턴 생성과 오디오 렌더링을 수행합니다.

## 파이프라인 흐름

```
원본 오디오
    ↓
separator.py (Demucs) → 드럼 스템 추출
    ↓
detector.py (4밴드 온셋) → 온셋 샘플 인덱스
    ↓
slicer.py (슬라이싱) → 개별 히트 WAV + kit_manifest.json
    ↓
dedup.py (MFCC+DSP) → 중복 제거, 대표 샘플 선택
    ↓
features.py (DSP 특징) → 에너지, 선명도, 주파수 밴드, 어택/디케이
    ↓
scoring.py (역할 분류) → 가중 공식 기반 5역할 점수 + softmax
    ↓
pool_balancer.py (풀 균형) → 역할별 최소 샘플 수 제약 적용
    ↓
events.py (그리드 생성) → EventGrid/DrumEvent, generate_skeleton()
    ↓
sequencer.py (렌더링) → WAV 오디오 출력
```

## 모듈 설명

| 모듈 | 설명 |
|------|------|
| `separator.py` | Demucs subprocess 호출, 혼합 오디오에서 드럼 스템 추출 |
| `detector.py` | 4밴드(저/중/고/초고) 스펙트럼 플럭스 기반 온셋 검출, merge 윈도우 적용 |
| `slicer.py` | 온셋 시점 기준 히트 슬라이싱, 페이드아웃, 무음 트리밍, 키트 저장 |
| `dedup.py` | MFCC(13차원) + DSP(7차원) = 20차원 벡터, 코사인 거리 기반 계층적 클러스터링, 클러스터당 대표 샘플 1개 선택 |
| `features.py` | DSP 특징 추출: 에너지, 선명도(스펙트럼 플럭스), 저/중/고 주파수 밴드 에너지 비율, 어택/디케이 시간 |
| `scoring.py` | DrumRole enum(CORE/ACCENT/MOTION/FILL/TEXTURE), 5가지 가중 공식 기반 역할 스코어링, softmax 정규화 |
| `pool_balancer.py` | 역할별 최소 샘플 수 제약(min_core, min_accent, min_motion), 부족 시 2순위 역할에서 재분배 |
| `events.py` | EventGrid/DrumEvent 데이터클래스, JSON 직렬화, generate_skeleton() 스켈레톤 패턴 생성 |
| `sequencer.py` | EventGrid → 오디오 렌더링, 리버브(선택), 볼륨 정규화 |
| `editor.py` | 그리드 편집 CLI: set(이벤트 추가), remove(제거), velocity(속도 조절), render(렌더링), export-midi(MIDI 내보내기) |
| `config.py` | PipelineConfig, SequencerConfig 데이터클래스, 핵심 파라미터 정의 |
| `cli.py` | argparse 기반 CLI 진입점, 명령 라우팅 |
| `run_pipeline.py` | 전체 파이프라인 오케스트레이터: 단일/다중 파일 처리, 킷 병합, 테스트 루프 생성 |
| `ingest.py` | 데이터셋 스캔, 통계 생성, 랜덤 샘플링 |
| `utils.py` | 로깅 설정, 오디오 I/O, 디렉토리 유틸리티 |
| `classifier.py` | 스펙트럼 특성(centroid, ZCR, 피치) 기반 드럼 클래스 분류(선택사항) |
| `embeddings.py` | MFCC/벡터 임베딩 유틸 |
| `humanize.py` | 타이밍 휴머나이제이션(마이크로 오프셋) |
| `test_synth.py` | 빠른 테스트용 루프 생성 함수 |

## 주요 설정 (config.py)

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `sr` | 44100 | 샘플링 레이트(Hz) |
| `demucs_model` | "htdemucs" | Demucs 모델 ("htdemucs", "mdx_extra" 등) |
| `demucs_device` | "cuda" | 디바이스 ("cuda" 또는 "cpu") |
| `chunk_duration_s` | 60.0 | Demucs 청크 크기(긴 파일 메모리 절약) |
| `onset_merge_ms` | 30.0 | 온셋 병합 윈도우(ms, 중복 방지) |
| `onset_backtrack` | True | 온셋 시점 백트래킹(피크 찾기) |
| `max_hit_duration_s` | 2.0 | 최대 히트 길이(s, 초과 시 버림) |
| `fade_out_ms` | 50.0 | 페이드아웃 길이(ms, 클릭음 제거) |
| `trim_silence_db` | 70.0 | 무음 트리밍 임계값(dB) |
| `dedup_enabled` | True | 중복 제거 활성화 |
| `dedup_threshold` | 0.5 | 중복 제거 코사인 거리 임계값(0~1) |
| `min_hit_duration_s` | 0.0 | 최소 히트 길이 필터(s) |
| `alpha` | 1.0 | 규칙 vs 분류기 가중치(1.0=규칙만) |
| `tau` | 1.0 | 소프트맥스 온도(높을수록 확률 균등) |
| `pool_min_core` | 1 | CORE 역할 최소 샘플 수 |
| `pool_min_accent` | 1 | ACCENT 역할 최소 샘플 수 |
| `pool_min_motion` | 1 | MOTION 역할 최소 샘플 수 |
| `max_poly` | 3 | 스텝당 최대 동시 발음 수 |
| `n_files` | 5 | 파이프라인 처리 파일 수 |
| `best_per_class` | 10 | 마스터 킷 역할당 최대 샘플 수 |

## 5가지 드럼 역할

| 역할 | 음악적 기능 | 스코어링 기준 |
|------|-----------|-------------|
| **CORE** | 킥(Kick) 계열 기초 리듬 | 저주파(L) 40%, 빠른 어택 25%, 짧은 디케이 25%, 부드러움 10% |
| **ACCENT** | 스네어(Snare) 계열 강세 | 높은 에너지(E) 35%, 선명도(S) 35%, 중주파(M) 20%, 짧은 디케이 10% |
| **MOTION** | 하이햇(Hi-hat) 계열 리듬 | 고주파(H) 40%, 낮은 에너지 20%, 짧은 디케이 25%, 선명도 15% |
| **FILL** | 탐(Tom)/필인 임팩트 | 높은 에너지 30%, 긴 디케이(D) 35%, 선명도 25%, 중주파 10% |
| **TEXTURE** | 배경/FX/앰비언스 | 긴 디케이 45%, 부드러움 25%, 저/중주파 20%, 낮은 에너지 10% |

## CLI 사용법

### 기본 명령어

```bash
# 전체 파이프라인: 분리 → 검출 → 슬라이싱 → 분류 → 렌더링
python -m stage1_drumgenx build-kit input.wav --output-dir output/

# 온셋 검출만
python -m stage1_drumgenx detect drums.wav

# 온셋 검출 + 역할 분류
python -m stage1_drumgenx classify drums.wav

# 다중 파일 자동 파이프라인
python -m stage1_drumgenx pipeline --n-files 5 --bpm 120
```

### 그리드 편집

```bash
# 스켈레톤 패턴 생성
python -m stage1_drumgenx generate output.json --bpm 120 --bars 4

# ASCII 스코어 시각화
python -m stage1_drumgenx show output.json

# 특정 위치에 이벤트 추가
python -m stage1_drumgenx set output.json --bar 0 --step 4 --role accent --vel 0.8

# 이벤트 제거
python -m stage1_drumgenx remove output.json --bar 0 --step 4

# 속도 조절
python -m stage1_drumgenx velocity output.json --role core --scale 0.8

# 오디오 렌더링
python -m stage1_drumgenx render output.json --output out.wav --reverb

# MIDI 내보내기
python -m stage1_drumgenx export-midi output.json --output out.mid
```

### 데이터셋 스캔

```bash
# 데이터셋 통계 스캔(샘플 5개)
python -m stage1_drumgenx scan --sample-n 5
```

## EventGrid 데이터 구조

```json
{
  "bpm": 120.0,
  "meter": "4/4",
  "resolution": 16,
  "bars": 4,
  "kit_dir": "/path/to/kit",
  "events": [
    {
      "bar": 0,
      "step": 0,
      "role": "core",
      "sample_id": "core_001",
      "vel": 0.8,
      "dur_steps": 1,
      "micro_offset_ms": 0.0
    }
  ]
}
```

## 스켈레톤 패턴 (generate_skeleton)

자동 생성 기본 패턴:

- **CORE**: 매 마디 스텝 {0, 4, 8, 12} (Four-on-the-floor)
- **ACCENT**: 스텝 {4, 12} (백비트, 2/4박자 강조)
- **MOTION**: 필수 A셋 {2, 6, 10, 14} + B셋 랜덤 서브셋 (밀도 조절 가능)
- **FILL**: 4마디마다 마지막 마디, 스텝 {12, 13, 14, 15}
- **TEXTURE**: 마디 0, 스텝 0, 지속 16스텝(전체 길이)
- **폴리포니 제약**: 스텝당 최대 3개 동시 발음, 우선순위 CORE > ACCENT > FILL > MOTION > TEXTURE

## 저수준 API

```python
from stage1_drumgenx.features import extract_dsp_features
from stage1_drumgenx.scoring import calculate_role_scores, get_best_role
from stage1_drumgenx.slicer import build_kit_from_audio
from stage1_drumgenx.events import EventGrid, generate_skeleton
from stage1_drumgenx.sequencer import load_kit, render_and_save

# 특징 추출
features = extract_dsp_features(y, sr=44100)
# → {"energy": 0.7, "sharpness": 0.5, "band_low": 0.3, ...}

# 역할 스코어링
scores = calculate_role_scores(features)
# → {DrumRole.CORE: 0.6, DrumRole.ACCENT: 0.2, ...}

role, score = get_best_role(scores)
# → (DrumRole.CORE, 0.6)

# 킷 빌드
manifest_path, samples = build_kit_from_audio(y, sr, onsets, output_dir)

# 그리드 생성 및 렌더링
grid = generate_skeleton(bars=4, bpm=120)
kit = load_kit(kit_dir, sr=44100)
output_wav = render_and_save(grid, kit, output_path)
```

## 주요 개선사항

### 온셋 검출(detector.py)

- 4개 주파수 밴드(저: 0-200Hz, 중저: 200-1kHz, 중고: 1-8kHz, 고: 8kHz+)에서 스펙트럼 플럭스 계산
- 각 밴드 강도(strength) 합산으로 통합 온셋 강도 계산
- 병합 윈도우(기본 30ms)로 중복 온셋 제거

### 중복 제거(dedup.py)

- MFCC 13차원 + DSP 7차원 = 20차원 특징 벡터
- 코사인 거리 기반 계층적 클러스터링(scipy.cluster.hierarchy)
- 클러스터당 대표 샘플 1개 선택(각 클러스터 가장 가까운 샘플)

### 역할 분류(scoring.py)

- 순수 규칙 기반 선형 가중 공식
- 5개 역할 각 70점 만점
- 소프트맥스 정규화로 확률 변환
- Stage 2와 통합 가능(alpha 파라미터로 가중치 조절)

## 의존성

```
numpy, scipy, librosa, soundfile
torch, torchaudio (Demucs, 선택적 CLAP)
pyyaml, tqdm
demucs (subprocess 호출)
pretty_midi (MIDI 내보내기, 선택적)
```

## 설정 오버라이드

모든 CLI 명령은 명령행 인자로 기본값을 오버라이드 가능:

```bash
python -m stage1_drumgenx build-kit input.wav \
  --sr 44100 \
  --device cpu \
  --model htdemucs \
  --output-dir /custom/path
```

프로그래매틱하게:

```python
from stage1_drumgenx.config import PipelineConfig
from stage1_drumgenx.run_pipeline import process_single_file

config = PipelineConfig(
    sr=44100,
    demucs_model="htdemucs",
    demucs_device="cuda",
    dedup_enabled=True,
    dedup_threshold=0.5,
)

kit_dir = process_single_file(Path("input.wav"), Path("output/"), config)
```

## 출력 구조

```
output/
├── file_name/
│   ├── demucs/
│   │   ├── drums.wav
│   │   ├── bass.wav
│   │   └── ...
│   └── kit/
│       ├── core/
│       │   ├── core_001.wav
│       │   └── ...
│       ├── accent/
│       │   └── ...
│       ├── kit_manifest.json
│       └── dedup_report.json
```

## 주의사항

- **Demucs CUDA**: htdemucs는 CUDA 8GB+ 권장. CPU 모드는 느림.
- **Long Audio**: chunk_duration_s를 조절해 메모리 사용량 제어.
- **Onset Merge**: 너무 큰 merge_ms는 빠른 더블 킥 미탐, 너무 작으면 중복 증가.
- **Dedup Threshold**: 0.5 (기본값)는 보수적. 0.3~0.4는 더 공격적으로 제거.

## 다음 단계

- **Stage 2**: stage2_role_assignment/ — CLAP 기반 ML 강화 역할 할당
- **Stage 3**: stage3_beat_grid/ — 비트 그리드 및 장르별 패턴
- **Stage 4**: stage4_model_gen/ — GrooveAE 생성형 시퀀싱
