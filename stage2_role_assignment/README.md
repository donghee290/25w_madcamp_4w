# Stage 2: ML 강화 역할 할당

## 개요

Stage 2는 드럼 히트에 음악적 역할(Role)을 할당하는 최우선 단계입니다. 두 가지 주요 접근법을 결합합니다:

1. **DSP 규칙 기반 스코어링**: 에너지, 선명도, 주파수 분포, 어택/디케이 시간 등 신호처리 특징을 이용한 규칙 기반 점수 계산
2. **CLAP 임베딩 기반 스코어링**: Contrastive Language-Audio Pretraining(CLAP) 모델을 통한 의미론적 유사도 점수 계산

두 점수를 가중 평균(alpha 블렌딩)으로 결합하고, 가드 조건(Guard Rails)을 적용하여 부적절한 역할 할당을 억제합니다. 최종 결과는 역할별 풀(Pool)로 구성됩니다.

## 5가지 드럼 역할

| 역할 | 음악적 기능 | 전형적 악기 | 스코어링 특징 |
|------|-----------|-----------|-------------|
| **CORE** | 저음역 기초 리듬(킥) | Kick, Bass Drum | 저주파 에너지, 빠른 어택, 짧은 디케이 |
| **ACCENT** | 강한 강세(스네어) | Snare, Clap | 높은 에너지, 선명한 트랜지언트, 중음역 |
| **MOTION** | 고음역 리듬 유지(하이햇) | Hi-hat, Cymbal | 고주파 에너지, 낮은 에너지, 짧은 디케이 |
| **FILL** | 임팩트/필인(탐) | Tom, Perc Hit | 높은 에너지, 긴 디케이, 선명함 |
| **TEXTURE** | 배경/FX/앰비언스 | Reverb Tail, Ambience | 긴 디케이, 부드러움, 낮은 에너지 |

## 아키텍처

```
원본 히트 WAV
    |
    +----> dsp/audio_io.py (전처리)
            - 16kHz mono로 리샘플링
            - 무음 트림 및 피크 정규화
            |
            +----> dsp/features.py (DSP 특징 추출)
                   - 에너지, 선명도, 주파수 분포
                   - 어택/디케이 시간
                   - 스펙트럼 편평성, 영점교차율
                   |
                   +----> dsp/rule_scoring.py
                          - 규칙 기반 역할 점수
                          - softmax 정규화 (p_rule)
    |
    +----> clap/backend.py (CLAP 모델)
            - transformers ClapModel 로드
            - 오디오 임베딩 계산
            |
            +----> clap/scoring.py
                   - 역할 텍스트 임베딩 캐시
                   - 유사도 계산 (p_clap)
    |
    +----> fusion/fuse.py (점수 융합)
            - p_final = alpha * p_rule + (1-alpha) * p_clap
            - 정규화 및 confidence 계산
            |
            +----> fusion/guards.py (가드 조건)
                   - 부적절 역할 억제
                   - Confidence 기반 보정
    |
    +----> pool/build_pools.py (풀 구성)
            - 역할별 샘플 분류
            - 필수 풀 관리 및 승격
            - 과다 역할 재균형
    |
    v
SampleResult (역할 + 점수 + 특징)
```

## 모듈 설명

### `role_assigner.py`
**메인 API 클래스 `RoleAssigner`**

```python
from stage2_role_assignment import RoleAssigner, RoleAssignerConfig
from stage2_role_assignment.types import Role

# 설정 로드
cfg = RoleAssignerConfig.from_yaml("configs/role_assignment.yaml")
assigner = RoleAssigner(cfg)

# 파일 기준 처리
result = assigner.assign_file("drums/kick_sample.wav", sample_id="kick_001")
print(f"역할: {result.role}")  # Role.CORE
print(f"신뢰도: {result.scores.confidence:.3f}")

# 배열 기준 처리
import numpy as np
y = np.random.randn(16000)  # 1초, 16kHz mono
result = assigner.assign_audio(y, sr=16000, sample_id="audio_001")
```

**메서드:**
- `assign_file(filepath, sample_id)`: WAV 파일에서 역할 할당
- `assign_audio(y, sr, sample_id, filepath)`: 수치 배열에서 역할 할당

### `types.py`
**핵심 데이터클래스**

- **`Role`**: 5가지 역할 열거형 (CORE, ACCENT, MOTION, FILL, TEXTURE)
- **`DSPFeatures`**: 원샷 특징 모음 (energy, sharpness, attack_time, decay_time, 주파수 비율 등)
- **`ScoreVector`**: 역할별 점수 맵 + 헬퍼 메서드 (argmax, sorted, margin 등)
- **`ScoreBundle`**: 규칙/CLAP/최종 점수 및 신뢰도 포함
- **`SampleResult`**: 역할 할당 결과 (역할, 점수, 특징, 디버그 정보)
- **`RolePools`**: 역할별 샘플 리스트 모음

### `dsp/audio_io.py`
**오디오 전처리**

설정(`AudioLoadConfig`):
- `target_sr`: 목표 샘플레이트 (기본 16kHz, CLAP 표준)
- `mono`: 모노 변환 여부
- `max_duration_sec`: 최대 길이 (기본 2초)
- `trim_silence`: 무음 자동 트림
- `peak_normalize`: 피크 정규화

### `dsp/features.py`
**DSP 특징 추출**

계산되는 특징들:

| 특징 | 범위 | 의미 |
|------|------|------|
| `energy` | 0~1 | 최대 RMS 값 (정규화) |
| `sharpness` | 0~1 | 스펙트럼 플럭스 피크 (트랜지언트 강도) |
| `attack_time` | 0~1 | onset ~ peak의 90% 도달 시간 (초, 클립) |
| `decay_time` | 0~1 | peak ~ 30% 감쇠 시간 (초, 클립) |
| `low_ratio` | 0~1 | 저주파(20-150Hz) 에너지 비율 |
| `mid_ratio` | 0~1 | 중음역(150-2kHz) 에너지 비율 |
| `high_ratio` | 0~1 | 고주파(2-8kHz) 에너지 비율 |
| `spectral_flatness` | 0~1 | 노이즈성 (높을수록 노이즈 같음) |
| `zero_crossing_rate` | 0~1 | 영점교차율 (고역/노이즈 힌트) |

### `dsp/rule_scoring.py`
**규칙 기반 역할 점수 계산**

각 역할마다 DSP 특징의 가중 선형 조합으로 점수를 계산합니다:

```
score_CORE = 0.40*L + 0.25*A_fast + 0.25*D_short + 0.10*(1-S)
score_ACCENT = 0.35*E + 0.35*S + 0.20*M + 0.10*D_short
score_MOTION = 0.40*H + 0.20*(1-E) + 0.25*D_short + 0.15*S
score_FILL = 0.30*E + 0.35*D + 0.25*S + 0.10*M
score_TEXTURE = 0.45*D + 0.25*(1-S) + 0.20*(L+M) + 0.10*(1-E)
```

각 점수는 softmax 정규화로 확률로 변환됩니다.

**텍스처 패널티**: 타격성이 강한 샘플(날카로움 > 0.55, 디케이 짧음)이 TEXTURE로 분류되는 것을 억제합니다. 또한 노이즈성이 낮은 샘플도 TEXTURE 점수를 감점합니다.

### `clap/backend.py`
**CLAP 오디오 임베딩 엔진**

Hugging Face Transformers를 통해 CLAP 모델을 로드하고 오디오 임베딩을 계산합니다:

- 모델: `laion/clap-htsat-unfused` (기본값)
- 입력: 16kHz mono 오디오
- 출력: 오디오 임베딩 벡터 (512차원 기본)
- 풀링: mean (프레임 평균)

### `clap/scoring.py`
**CLAP 유사도 점수**

5가지 역할에 대한 텍스트 임베딩을 계산하고, 오디오 임베딩과의 코사인 유사도를 계산합니다:

```python
text_embeddings = {
    Role.CORE: embed("kick drum, bass drum"),
    Role.ACCENT: embed("snare, clap"),
    Role.MOTION: embed("hi-hat, hi hat cymbal"),
    Role.FILL: embed("tom, tom drum"),
    Role.TEXTURE: embed("reverb tail, ambient, noise"),
}

similarity = cosine_similarity(audio_embed, text_embeddings[role])
# softmax -> p_clap (확률)
```

텍스트 임베딩은 캐시되어 반복 계산을 피합니다. 프롬프트는 `prompts/prompts.yaml`에서 관리됩니다.

### `fusion/fuse.py`
**규칙 + CLAP 점수 융합**

```
p_final = alpha * p_rule + (1 - alpha) * p_clap
```

기본 `alpha = 0.9` (DSP 90%, CLAP 10%)로 설정되어, DSP 규칙을 주요 판단 근거로 하되 CLAP 모델의 의미론적 정보로 보정합니다.

선택적 role_bias로 특정 역할에 대한 사전(prior)을 추가할 수 있습니다.

### `fusion/guards.py`
**5가지 가드 조건**

부적절한 역할 할당을 억제하는 규칙들입니다. 특징이나 confidence에 따라 최종 점수를 보정합니다:

1. **Texture Suppress**: 타격성이 강한 샘플(S > 0.60, D_short < 0.32)의 TEXTURE 점수 * 0.60
2. **Sustained Noise Suppress**: 지속적/노이즈성 샘플(D > 0.70, flatness > 0.25)의 CORE/ACCENT 점수 억제
3. **Motion Min Condition**: MOTION이 고주파/짧은 디케이 조건을 충족하지 않으면 점수 * 0.70
4. **Fill Conservative**: FILL은 확신할 때만 (p_fill > 0.35 AND margin > 0.12)
5. **Low Confidence Texture Extra**: Confidence 낮고 TEXTURE가 1등이면서 타격계 역할이 2등일 때 추가 억제

모든 가드는 설정 가능하며 YAML에서 제어됩니다.

### `pool/build_pools.py`
**풀 구성 및 관리**

샘플들을 역할별로 분류하고, 풀 제약 조건을 관리합니다:

**필수 풀**: CORE, ACCENT, MOTION은 반드시 1개 이상 필요
**선택 풀**: FILL, TEXTURE는 0개도 가능

**제약 조건**:
- 상한선 (max_sizes): CORE/ACCENT/MOTION의 최대 개수
- 승격 (promote_when_missing): 필수 풀이 비었을 때, 다음 후보를 승격하되 특정 조건 위반 검사
- 재균형 (rebalance_when_excess): 상한선 초과 시, margin이 작은 샘플을 다른 역할로 이동

## 설정 관리

모든 파라미터는 `configs/role_assignment.yaml`에서 관리됩니다.

### 주요 설정 항목

**Audio (전처리)**
```yaml
audio:
  target_sr: 16000        # CLAP 표준
  mono: true
  max_duration_sec: 2.0
  trim_silence: true
  peak_normalize: true
  peak_target: 0.95
```

**DSP (특징 추출)**
```yaml
dsp:
  band_edges_hz:
    low: [20, 150]
    mid: [150, 2000]
    high: [2000, 8000]
  attack_window_sec: 0.08
  decay_window_sec: 0.60
```

**Rule Scoring (규칙 점수)**
```yaml
rule_scoring:
  weights:
    core:
      L: 0.40           # 저주파 비율
      A_fast: 0.25      # 빠른 어택
      D_short: 0.25     # 짧은 디케이
      one_minus_S: 0.10 # 낮은 선명도
    # ... (ACCENT, MOTION, FILL, TEXTURE)

  texture_penalty:
    enabled: true
    transient_S_threshold: 0.55
    decay_short_threshold: 0.35
    penalty: 0.18
```

**CLAP (오디오-언어 모델)**
```yaml
clap:
  backend: "transformers"
  model_id: "laion/clap-htsat-unfused"
  audio_pooling: "mean"
  tau_clap: 0.07                    # softmax 온도
  cache_text_embeddings: true
  cache_dir: ".cache/clap_text"
```

**Fusion (점수 결합)**
```yaml
fusion:
  alpha: 0.9                        # DSP 90%, CLAP 10%
  confidence_margin_threshold: 0.12
```

**Guards (가드 조건)**
```yaml
guards:
  enabled: true
  texture_suppress:
    transient_S_threshold: 0.60
    multiply: 0.60
  # ... (나머지 5가지 가드)
```

**Pool (풀 관리)**
```yaml
pool:
  required_roles: ["CORE", "ACCENT", "MOTION"]
  max_sizes:
    CORE: 4
    ACCENT: 4
    MOTION: 10
  promote_when_missing:
    enabled: true
  rebalance_when_excess:
    enabled: true
    min_margin_keep: 0.08
```

## 사용법

### 단일 파일 처리

```bash
# YAML 설정 로드 및 RoleAssigner 초기화
python -c "
from stage2_role_assignment import RoleAssigner
from stage2_role_assignment.types import Role
import yaml

with open('stage2_role_assignment/configs/role_assignment.yaml') as f:
    cfg_dict = yaml.safe_load(f)

assigner = RoleAssigner.from_dict(cfg_dict)
result = assigner.assign_file('samples/kick.wav')
print(f'역할: {result.role}')
print(f'신뢰도: {result.scores.confidence:.3f}')
print(f'점수: {result.scores.final.sorted()}')
"
```

### 배치 처리

```python
from pathlib import Path
from stage2_role_assignment import RoleAssigner, RoleAssignerConfig
from stage2_role_assignment.types import RolePools
import json

# 설정 로드
cfg = RoleAssignerConfig.from_yaml("stage2_role_assignment/configs/role_assignment.yaml")
assigner = RoleAssigner(cfg)

# 샘플 디렉토리 스캔
samples_dir = Path("samples/drum_hits")
results = []

for wav_file in samples_dir.glob("*.wav"):
    result = assigner.assign_file(wav_file)
    results.append(result)
    print(f"{wav_file.name}: {result.role}")

# 풀 구성
pools = build_pools(results)
print(f"CORE: {len(pools.core)}")
print(f"ACCENT: {len(pools.accent)}")
print(f"MOTION: {len(pools.motion)}")

# 결과 저장
with open("output/role_pools.json", "w") as f:
    json.dump(pools.as_dict(), f)
```

### 디버깅 및 상세 점수 확인

```python
result = assigner.assign_file("samples/kick.wav")

print("=== DSP Features ===")
print(f"Energy: {result.features.energy:.3f}")
print(f"Sharpness: {result.features.sharpness:.3f}")
print(f"Attack Time: {result.features.attack_time:.3f}s")
print(f"Decay Time: {result.features.decay_time:.3f}s")
print(f"Low:Mid:High = {result.features.low_ratio:.2f}:{result.features.mid_ratio:.2f}:{result.features.high_ratio:.2f}")

print("\n=== Scores ===")
print("Rule:", result.scores.rule.sorted())
print("CLAP:", result.scores.clap.sorted())
print("Final:", result.scores.final.sorted())
print(f"Confidence: {result.scores.confidence:.3f}")

print("\n=== Raw Scores ===")
print("Rule raw:", result.rule_raw_scores)
print("CLAP sim:", result.clap_similarities)
```

## 출력 형식

### SampleResult (단일 샘플)

```python
@dataclass
class SampleResult:
    sample_id: str                      # "kick_001"
    filepath: str                       # "/path/to/kick.wav"

    role: Role                          # Role.CORE
    scores: ScoreBundle                 # 모든 점수
    features: DSPFeatures              # 추출된 특징들

    clap_similarities: Dict[str, float] # {"CORE": 0.82, ...}
    rule_raw_scores: Dict[str, float]   # {"CORE": 2.15, ...}
```

### RolePools (배치 결과)

```python
@dataclass
class RolePools:
    core: List[SampleResult]           # CORE 역할 샘플들
    accent: List[SampleResult]         # ACCENT 역할 샘플들
    motion: List[SampleResult]         # MOTION 역할 샘플들
    fill: List[SampleResult]           # FILL 역할 샘플들
    texture: List[SampleResult]        # TEXTURE 역할 샘플들
```

## 의존성

핵심:
- `numpy`, `scipy`: 수치 계산
- `librosa`: 오디오 처리 및 특징 추출
- `soundfile`: WAV I/O
- `resampy`: 리샘플링
- `pyyaml`: 설정 로드

ML:
- `torch`, `torchaudio`: 딥러닝 추론
- `transformers`: CLAP 모델 로드

## 주요 설계 결정사항

1. **알파 블렌딩**: CLAP만으로는 의도치 않은 분류가 발생할 수 있으므로, DSP 규칙을 주요 근거(0.9)로 유지하고 CLAP(0.1)으로 보정합니다.

2. **가드 레일**: 규칙과 머신러닝의 결합에서도 명확한 부적절성(예: TEXTURE인데 날카로운 타격)을 막기 위해 명시적 가드 조건을 두었습니다.

3. **텍스처 억제**: TEXTURE는 배경음/FX 역할이므로 타격성이 강한 샘플이 TEXTURE로 빠지는 것을 적극 방지합니다.

4. **풀 제약**: 필수 역할(CORE, ACCENT, MOTION)을 보장하되, 상한선으로 풀의 크기를 제어합니다. 부족하면 승격, 초과하면 재균형합니다.

5. **16kHz Mono**: CLAP의 표준 입력에 맞춰 모든 오디오를 16kHz mono로 통일합니다. 이는 계산 효율성도 높입니다.

## 문제 해결

### CLAP 모델 다운로드 실패
첫 실행 시 CLAP 모델(`laion/clap-htsat-unfused`)을 자동으로 다운로드합니다. 인터넷이 느리면 timeout이 발생할 수 있습니다. 이 경우:

```bash
# 수동으로 캐시 다운로드
python -c "from transformers import AutoModel; AutoModel.from_pretrained('laion/clap-htsat-unfused')"
```

### CUDA 메모리 부족
CLAP 추론이 CUDA 메모리를 많이 사용합니다. 배치 크기를 줄이거나 CPU로 실행합니다:

```python
cfg.clap_backend.device = "cpu"
assigner = RoleAssigner(cfg)
```

### 특정 역할로만 분류됨
모든 샘플이 한 역할(예: TEXTURE)로 분류된다면:

1. YAML의 `guards` 활성화 여부 확인
2. `rule_scoring.weights` 균형 검토 (특정 역할 가중치 과다)
3. 텍스처 패널티 임계값 재조정

### 신뢰도(Confidence)가 매우 낮음
top-2 점수가 매우 가깝다면, 특징이 모호한 샘플입니다. 신뢰도 기준을 낮추거나, 추가 제약을 약화할 수 있습니다.

## 참고 문헌

- CLAP 모델: https://github.com/LAION-AI/CLAP
- librosa: https://librosa.org/
- Contrastive Learning: https://arxiv.org/abs/2102.01169
