# 오늘 작업 요약 + 전체 흐름

## 전체 흐름 (요약)
1) Stage 1 전처리  
원본 오디오 → 온셋 검출 → 히트 슬라이싱 → 중복 제거(MFCC+DSP) → 더미 샘플

2) Stage 2 역할 할당  
원샷 샘플 → DSP 규칙 + CLAP 융합 → 역할(CORE/ACCENT/MOTION/FILL/TEXTURE) 분류 → 풀 생성

3) Stage 3 비트 생성  
BPM 그리드 → 스켈레톤 패턴 → 이벤트 JSON 출력

4) Stage 4 모델 변형(선택)  
GrooVAE 변형용 NoteSequence 변환(현재 더미 러너)

---

## 오늘 한 작업
- Flask 백엔드 스캐폴딩 추가 (`app/`, `wsgi.py`)
- MongoDB 저장소 구현 및 Atlas 연결 테스트
- 전처리 출력 길이 1.5~2.5초로 고정 가능(패딩/트림)
- 중복 제거를 MFCC+DSP 클러스터링으로 변경
- 전처리 원스텝 실행 스크립트 추가 (`pipeline/run_preprocess_all.py`)
- API JSON 파싱 보강 (pools_json 직접 전달 경로)

---

## 전처리 원스텝 실행 (1.5~2.5초)
```bash
python pipeline/run_preprocess_all.py --limit 5 --skip_demucs
```

옵션:
- `--min_sec` / `--max_sec` : 출력 길이 (기본 1.5~2.5초)
- `--dedup_threshold` : 중복 제거 강도 (낮을수록 다양)
- `--skip_demucs` : Demucs 없이 원본 오디오로 처리

개별 실행 예시:
```bash
python pipeline/run_preprocess.py \
  --dataset_root "C:\path\to\audio_root" \
  --output_root "dummy_dataset_custom" \
  --limit 5 \
  --min_sec 1.5 \
  --max_sec 2.5 \
  --dedup_threshold 0.5 \
  --skip_demucs
```

---

## 백엔드 (Flask + MongoDB)

### 환경변수 (Atlas or Local)
```
SOUNDROUTINE_DB_BACKEND=mongo
SOUNDROUTINE_MONGO_URI=mongodb://localhost:27017
SOUNDROUTINE_MONGO_DB=soundroutine
SOUNDROUTINE_MONGO_COLLECTION=jobs
```

Atlas 사용 시 `SOUNDROUTINE_MONGO_URI`만 `mongodb+srv://...`로 변경.

### 실행
```bash
python -m flask --app wsgi:app run --host 0.0.0.0 --port 8000
```

### 테스트 (pools_json 직접 전달)
```bash
curl -X POST http://127.0.0.1:8000/v1/beat \
  -H "Content-Type: application/json" \
  -d '{
    "bpm":120,
    "bars":4,
    "pools_json":{
      "CORE_POOL":[{"sample_id":"c1","features":{"energy":0.8,"decay_time":0.1}}],
      "ACCENT_POOL":[{"sample_id":"a1","features":{"energy":0.7,"decay_time":0.1}}],
      "MOTION_POOL":[{"sample_id":"m1","features":{"energy":0.3,"decay_time":0.05}}],
      "FILL_POOL":[],
      "TEXTURE_POOL":[{"sample_id":"t1","features":{"energy":0.2,"decay_time":0.9}}]
    }
  }'
```

성공 시 `job_id` 반환 → MongoDB `soundroutine.jobs`에 저장됨.
