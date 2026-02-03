#!/bin/bash
##############################################################################
# MongoDB Atlas SSH Tunnel Setup Script
# 
# 내부망에서 27017 포트가 차단된 경우, VPS를 경유하여 MongoDB Atlas에 접속합니다.
# 
# 아키텍처:
#   내부망 → VPS (SSH) → MongoDB Atlas
#   localhost:27017 → VPS → xxxxx.mongodb.net:27017
#
# 사용법:
#   chmod +x setup-mongodb-tunnel.sh
#   ./setup-mongodb-tunnel.sh
##############################################################################

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

#=============================================================================
# 설정 변수 (환경변수 또는 기본값 사용)
#=============================================================================
VPS_USER="${VPS_USER:-ubuntu}"
VPS_HOST="${VPS_HOST:-your-vps-ip}"
VPS_SSH_PORT="${VPS_SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-~/.ssh/id_rsa}"

# MongoDB Atlas 클러스터 정보
# Atlas Dashboard > Connect > Shell에서 확인 가능
# 형식: cluster0-shard-00-00.xxxxx.mongodb.net
MONGO_SHARD_0="${MONGO_SHARD_0:-cluster0-shard-00-00.xxxxx.mongodb.net}"
MONGO_SHARD_1="${MONGO_SHARD_1:-cluster0-shard-00-01.xxxxx.mongodb.net}"
MONGO_SHARD_2="${MONGO_SHARD_2:-cluster0-shard-00-02.xxxxx.mongodb.net}"
MONGO_PORT="${MONGO_PORT:-27017}"

#=============================================================================
# 1. 27017 포트 연결 테스트
#=============================================================================
echo ""
log_info "MongoDB Atlas 직접 연결 테스트 중..."

if timeout 5 bash -c "echo > /dev/tcp/${MONGO_SHARD_0}/${MONGO_PORT}" 2>/dev/null; then
    log_info "✅ MongoDB Atlas에 직접 연결할 수 있습니다!"
    log_info "터널링이 필요하지 않습니다."
    echo ""
    echo "연결 문자열을 그대로 사용하세요:"
    echo "  mongodb+srv://username:password@cluster.mongodb.net/"
    exit 0
else
    log_warn "❌ MongoDB Atlas에 직접 연결할 수 없습니다."
    log_info "SSH 터널링을 설정합니다..."
fi

#=============================================================================
# 2. VPS 연결 테스트
#=============================================================================
echo ""
log_info "VPS SSH 연결 테스트 중..."

if ssh -o ConnectTimeout=5 -o BatchMode=yes -i "$SSH_KEY" -p "$VPS_SSH_PORT" "${VPS_USER}@${VPS_HOST}" "echo 'SSH OK'" 2>/dev/null; then
    log_info "✅ VPS SSH 연결 성공!"
else
    log_error "❌ VPS에 SSH 연결할 수 없습니다."
    log_error "SSH 키와 VPS 정보를 확인하세요."
    exit 1
fi

#=============================================================================
# 3. SSH 터널 시작 (autossh 사용)
#=============================================================================
echo ""
log_info "MongoDB SSH 터널 시작 중..."

# 기존 터널 프로세스 종료
pkill -f "ssh.*27017.*mongodb" 2>/dev/null || true
pkill -f "autossh.*27017.*mongodb" 2>/dev/null || true

# autossh가 설치되어 있는지 확인
if ! command -v autossh &> /dev/null; then
    log_warn "autossh가 설치되어 있지 않습니다. ssh를 대신 사용합니다."
    log_warn "autossh 설치: sudo apt-get install autossh"
    
    # SSH 터널 (백그라운드 실행)
    ssh -f -N \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -i "$SSH_KEY" \
        -p "$VPS_SSH_PORT" \
        -L "27017:${MONGO_SHARD_0}:${MONGO_PORT}" \
        -L "27018:${MONGO_SHARD_1}:${MONGO_PORT}" \
        -L "27019:${MONGO_SHARD_2}:${MONGO_PORT}" \
        "${VPS_USER}@${VPS_HOST}"
else
    # autossh 터널 (자동 재연결)
    export AUTOSSH_GATETIME=0
    export AUTOSSH_POLL=30
    
    autossh -M 0 -f -N \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -i "$SSH_KEY" \
        -p "$VPS_SSH_PORT" \
        -L "27017:${MONGO_SHARD_0}:${MONGO_PORT}" \
        -L "27018:${MONGO_SHARD_1}:${MONGO_PORT}" \
        -L "27019:${MONGO_SHARD_2}:${MONGO_PORT}" \
        "${VPS_USER}@${VPS_HOST}"
fi

sleep 2

#=============================================================================
# 4. 터널 연결 확인
#=============================================================================
echo ""
log_info "터널 연결 확인 중..."

if timeout 5 bash -c "echo > /dev/tcp/localhost/27017" 2>/dev/null; then
    log_info "✅ MongoDB 터널이 활성화되었습니다!"
else
    log_error "❌ 터널 연결에 실패했습니다."
    exit 1
fi

#=============================================================================
# 5. 완료 메시지
#=============================================================================
echo ""
echo "=============================================="
log_info "MongoDB SSH 터널 설정 완료!"
echo "=============================================="
echo ""
echo "터널링된 연결 문자열:"
echo -e "  ${BLUE}mongodb://localhost:27017,localhost:27018,localhost:27019/soundroutine?replicaSet=atlas-xxxxxx${NC}"
echo ""
echo "또는 단일 샤드 연결:"
echo -e "  ${BLUE}mongodb://localhost:27017/soundroutine${NC}"
echo ""
echo ".env 파일에 설정:"
echo "  SOUNDROUTINE_MONGO_URI=mongodb://localhost:27017"
echo ""
echo "터널 상태 확인:"
echo "  ps aux | grep 'ssh.*27017'"
echo ""
echo "터널 종료:"
echo "  pkill -f 'autossh.*27017' || pkill -f 'ssh.*27017'"
echo ""
