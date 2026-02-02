# SoundRoutine Backend Plan (Basic Beat Only)

본 계획은 **기본 비트 생성(그루브/모델 변형 제외)**을 목표로 하며,
현 레포의 Stage 1~3 구성요소를 재사용해 **Flask + NoSQL(DjangoDB) 기반 API 서버**를 구성합니다.
배포 환경은 **KAIST 내부 kcloud GPU 서버**이며, 외부 노출은 **Reverse SSH Tunneling + External VPS + Nginx**로 처리합니다.

---

## 0) 범위/가정

- **목표**: 원샷(또는 짧은) 오디오 → 역할 분류 → 기본 비트 스켈레톤 생성 → JSON 출력
- **비포함**: GrooVAE 실제 추론, 마이크로타이밍 그루브, 실시간 스트리밍
- **NoSQL (DjangoDB)**: 정확한 엔진 확정 필요
  - 가정: MongoDB 계열(예: Djongo/MongoEngine) 또는 DynamoDB 스타일
  - 계획에는 DB 추상화 레이어를 두어 엔진 교체 가능하게 설계

---

## 1) 아키텍처 개요

```
Client
  → External VPS (Nginx)
    → Reverse SSH Tunnel
      → kcloud (Flask API) → NoSQL DB
                        └→ Stage2 role assignment
                        └→ Stage3 beat grid/skeleton
```

- **Flask API**: REST endpoints 제공
- **Stage2**: 역할 분류 (DSP + CLAP)
- **Stage3**: 그리드/스켈레톤 생성
- **DB**: 요청/결과 저장, 재현성 유지

---

## 2) API 설계 (초안)

### 2.1 `POST /v1/beat`
**입력**
- `bpm` (float, required)
- `bars` (int, default=4)
- `samples` (파일 업로드 또는 샘플 경로 리스트)
- `mode` (optional): `"oneshot"` | `"preprocess"` (long audio → Stage1)

**동작**
- `oneshot`: Stage2 role assignment → pools JSON
- `preprocess`: Stage1 → 샘플 추출 → Stage2 → pools JSON
- Stage3: skeleton/grid 생성

**출력**
- `grid_json`
- `events_json`
- `meta` (선택된 샘플, 역할 분포)

### 2.2 `GET /v1/beat/{job_id}`
- 비동기 확장용 (현재는 동기 처리 예정)

### 2.3 `GET /health`
- 서버/의존성 상태 확인

---

## 3) 내부 모듈 구조 (Flask)

```
app/
  api.py             # Flask endpoints
  services/
    role_assign.py   # Stage2 wrapper
    beat_gen.py      # Stage3 wrapper
    preprocess.py    # Stage1 wrapper (옵션)
  db/
    repository.py    # DB 추상화
    models.py        # 요청/결과 schema
  config.py
```

- `services/`는 기존 stage1~3 코드를 직접 호출
- DB는 요청/결과 + 메타만 저장

---

## 4) 배포/네트워크 설계

### 4.1 kcloud (내부망)
- Flask 서버는 `0.0.0.0:8000` (내부 전용)
- **Reverse SSH Tunnel**:
  - `autossh -M 0 -N -R 0.0.0.0:9000:localhost:8000 user@VPS`
  - kcloud → VPS로 터널 생성

### 4.2 External VPS (외부망)
- Nginx가 `https://your-domain` 수신
- `proxy_pass http://127.0.0.1:9000`
- TLS 종료는 VPS에서 처리

---

## 5) Docker 패키징 (서버에서 진행)

**이미지 목표**
- Python 3.10+
- `requirements.txt` 설치
- `app/` 구동 (gunicorn or flask)

**kcloud 실행 예**
```
docker run -d --name soundroutine \
  -p 8000:8000 \
  --gpus all \
  -e APP_ENV=prod \
  soundroutine:latest
```

**Tunnel**
```
autossh -M 0 -N -R 0.0.0.0:9000:localhost:8000 user@VPS
```

---

## 6) 단계별 구현 계획

### Phase 1: 로컬 백엔드 구축
- Flask 앱 생성 + 최소 1개 엔드포인트(`/v1/beat`)
- Stage2/Stage3 wrapper 서비스 구현
- JSON 응답 정상 생성 확인

### Phase 2: DB 연동
- NoSQL DB 연결 (DjangoDB 확정 필요)
- Request/Result 저장
- `job_id` 기반 조회 지원

### Phase 3: 배포 준비
- Dockerfile 작성 (서버에서 빌드)
- 환경변수 정리 (.env)
- Nginx + Reverse SSH 구성 문서화

---

## 7) 내가 해야 할 일 (사용자 작업)

1) **NoSQL 엔진 확정**
   - “DjangoDB”가 정확히 어떤 제품인지 결정 필요
2) **External VPS 준비**
   - 도메인 연결, 80/443 오픈, Nginx 설치
3) **kcloud 접근 정보 제공**
   - SSH 계정, 포트, GPU 사용 가능 여부 확인
4) **오디오 입력 방식 확정**
   - 원샷 업로드만? 혹은 긴 오디오 → Stage1 사용?
5) **보안 정책**
   - API Key / JWT 여부 결정

---

## 8) 다음 작업 제안

- Flask 최소 API 스캐폴딩 추가
- `services/role_assign.py`, `services/beat_gen.py` 작성
- `BACKEND_PLAN.md` 기반 TODO 체크리스트 생성

---

원하면 다음 단계로 **Flask 스캐폴딩 + 엔드포인트 골격**까지 바로 만들 수 있습니다.
