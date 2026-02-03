# SoundRoutine 인프라 구조

## 핵심 개념
**내부 서버(GPU 서버)에는 고정 IP가 없다.**
따라서 외부에서 접속하려면 **VPS(고정 IP 보유)**를 거쳐야 한다.

---

## 구조도

```
[사용자 브라우저]
        |
        v
[도메인: routine.n-e.kr 또는 n-e.kr]
        |
        v (DNS -> VPS IP)
[VPS (192.249.19.253)]
   - Nginx (80/443)
   - SSH 터널 수신측 (localhost:8080)
        |
        v (Reverse SSH Tunnel)
[내부 서버 (camp-gpu-20)]
   - Flask Backend (8000)
   - 로컬 Nginx (80)
   - React Frontend (3000, 선택)
```

---

## 각 컴포넌트 역할

### 1. VPS (외부 접속 창구)
- **IP:** `192.249.19.253`
- **User:** `ubuntu`
- **역할:** 외부에서 접속 가능한 유일한 진입점
- **Nginx 설정:** `/etc/nginx/nginx.conf` (또는 sites-available)
  - 80/443 포트로 요청 받음
  - `proxy_pass http://127.0.0.1:8080` 으로 터널에 전달

### 2. SSH Tunnel (autossh)
- **명령어:** 
  ```bash
  autossh -M 0 -N -R 8080:localhost:8000 -o ServerAliveInterval=30 -i ~/.ssh/id_rsa ubuntu@192.249.19.253
  ```
- **의미:** VPS의 `localhost:8080` -> 내부 서버의 `localhost:8000` 연결
- **내부 서버에서 실행**해야 함 (VPS가 아님!)

### 3. 내부 서버 (camp-gpu-20)
- **Flask:** 포트 8000
  - `python -m backend.api`
  - `.env`의 `EXTERNAL_BASE_URL` 설정 중요
- **Nginx (선택):** 포트 80
  - 로컬에서 Flask/React를 묶어서 서빙
  - 설정: `/etc/nginx/sites-available/soundroutine`

### 4. 도메인 & DNS
- **도메인:** `n-e.kr` 또는 `routine.n-e.kr`
- **DNS 설정:** A 레코드가 VPS IP(`192.249.19.253`)를 가리켜야 함
- **Cloudflare 사용 시:** Cloudflare DNS에서 A 레코드 설정

---

## 체크리스트 (문제 발생 시)

### 접속이 안 될 때
1. **VPS Nginx 실행 중?** → `ssh ubuntu@192.249.19.253 "systemctl status nginx"`
2. **SSH 터널 살아있음?** → `ps aux | grep autossh`
3. **Flask 실행 중?** → `ps aux | grep api.py`
4. **DNS 설정됨?** → `dig +short n-e.kr` 결과가 `192.249.19.253` 이어야 함

### 구글 로그인 안 될 때 (redirect_uri_mismatch)
1. `.env`의 `EXTERNAL_BASE_URL`이 실제 접속 도메인과 일치하는지 확인
2. 구글 클라우드 콘솔에 리다이렉트 URI 등록되어 있는지 확인:
   - `https://[도메인]/api/auth/google/callback`

---

## 실행 순서

```bash
# 1. VPS에서 Nginx 실행 (한 번만)
ssh ubuntu@192.249.19.253 "sudo systemctl start nginx"

# 2. 내부 서버에서 SSH 터널 실행
autossh -M 0 -N -R 8080:localhost:8000 -o ServerAliveInterval=30 -i ~/.ssh/id_rsa ubuntu@192.249.19.253 &

# 3. 내부 서버에서 Flask 실행
cd /home/my_project/25w_madcamp_4w
python -m backend.api

# 4. 브라우저에서 접속
# https://routine.n-e.kr 또는 설정된 도메인
```

---

## 주의사항

- **Cloudflare Tunnel (cloudflared)은 이 구조에서 필요 없음!**
  - VPS가 고정 IP 역할을 대신함
  - cloudflared는 VPS 없이 직접 연결할 때만 사용

- **Quick Tunnel은 테스트용**
  - URL이 매번 바뀜
  - 프로덕션에서는 사용 불가

---

## 파일 위치

| 파일 | 위치 | 설명 |
|------|------|------|
| Flask 설정 | `/home/my_project/25w_madcamp_4w/.env` | EXTERNAL_BASE_URL 등 |
| 로컬 Nginx | `/etc/nginx/sites-available/soundroutine` | 로컬 프록시 설정 |
| VPS Nginx | `/home/my_project/25w_madcamp_4w/infra/vps/nginx.conf` | VPS에 복사해서 사용 |
| Docker 설정 | `/home/my_project/25w_madcamp_4w/docker-compose.yml` | 배포용 |
