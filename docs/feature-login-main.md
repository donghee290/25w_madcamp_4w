# Feature: 로그인/회원가입/메인 페이지

## 개요
사용자 인증(로그인, 회원가입) 및 메인 랜딩 페이지 구현

---

## Frontend

### 페이지 구성

| 파일 | 경로 | 설명 |
|------|------|------|
| `LandingPage.tsx` | `/` | 메인 랜딩 페이지 |
| `LoginPage.tsx` | `/login` | 로그인 페이지 |
| `SignupPage.tsx` | `/signup` | 회원가입 페이지 |
| `StudioPage.tsx` | `/studio` | 스튜디오 페이지 |

### 스타일

| 파일 | 설명 |
|------|------|
| `LandingPage.css` | 랜딩 페이지 스타일 |
| `AuthPage.css` | 로그인 페이지 스타일 |
| `SignupPage.css` | 회원가입 페이지 스타일 |
| `StudioPage.css` | 스튜디오 페이지 스타일 |
| `index.css` | 전역 스타일 |

### 이미지 에셋

| 파일 | 설명 |
|------|------|
| `logo.png` | SoundRoutine 로고 |
| `Sign in.png` | 로그인 페이지 배경 |
| `Sign up.png` | 회원가입 페이지 배경 |

### API

| 파일 | 설명 |
|------|------|
| `authApi.ts` | 인증 관련 API 호출 함수 |

---

## Backend

### 서버 설정

| 파일 | 설명 |
|------|------|
| `server.js` | Express 서버 (포트 5000) |
| `package.json` | 패키지 의존성 |

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/auth/register` | 회원가입 |
| POST | `/auth/login` | 로그인 |

### 데이터 모델

| 파일 | 컬렉션 | 필드 |
|------|--------|------|
| `UserAuth.js` | `auths` | id, password, createdAt |
| `UserInfo.js` | `users` | id, name, job |

### 유틸리티

| 파일 | 설명 |
|------|------|
| `reset_db.js` | DB 초기화 스크립트 |

---

## 실행 방법

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
npm install
node server.js
```

### 환경 변수

**Frontend** (`frontend/.env`)
```
VITE_API_BASE_URL=http://localhost:5000
```

**Backend** (`backend/.env`)
```
PORT=5000
MONGO_URI=mongodb://127.0.0.1:27017/soundroutine
JWT_SECRET=your_secret_key
```

---

## 요구사항

- Node.js 18+
- MongoDB (로컬 또는 Atlas)
