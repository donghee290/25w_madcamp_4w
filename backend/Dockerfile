##############################################################################
# Backend Dockerfile
# 
# Flask 백엔드 + Google OAuth + MongoDB 연동
##############################################################################

FROM python:3.11-slim

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 환경 변수 기본값
ENV FLASK_APP=backend.api:create_app
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# 데이터 디렉토리 생성
RUN mkdir -p /app/data

# 포트 노출
EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Gunicorn으로 실행
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "backend.api:create_app()"]
