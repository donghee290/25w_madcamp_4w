#!/bin/bash
##############################################################################
# VPS Reverse SSH Tunnel Setup Script
# 
# 이 스크립트는 VPS에서 실행하여 필요한 설정을 완료합니다.
# 
# 사용법:
#   chmod +x setup-vps-tunnel.sh
#   sudo ./setup-vps-tunnel.sh
##############################################################################

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
# 1. 시스템 업데이트 및 필수 패키지 설치
#=============================================================================
log_info "시스템 패키지 업데이트 중..."
apt-get update && apt-get upgrade -y

log_info "필수 패키지 설치 중..."
apt-get install -y \
    nginx \
    certbot \
    python3-certbot-nginx \
    ufw \
    curl \
    htop

#=============================================================================
# 2. SSH 설정 (Reverse Tunneling 활성화)
#=============================================================================
log_info "SSH 설정 조정 중..."

# /etc/ssh/sshd_config에 GatewayPorts 설정 추가
if ! grep -q "^GatewayPorts yes" /etc/ssh/sshd_config; then
    echo "" >> /etc/ssh/sshd_config
    echo "# Enable reverse tunneling" >> /etc/ssh/sshd_config
    echo "GatewayPorts yes" >> /etc/ssh/sshd_config
    echo "ClientAliveInterval 60" >> /etc/ssh/sshd_config
    echo "ClientAliveCountMax 3" >> /etc/ssh/sshd_config
    log_info "SSH 설정이 업데이트되었습니다."
else
    log_info "SSH GatewayPorts가 이미 설정되어 있습니다."
fi

# SSH 서비스 재시작
systemctl restart sshd

#=============================================================================
# 3. 방화벽 설정
#=============================================================================
log_info "방화벽 설정 중..."

ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8080/tcp  # SSH 터널 포트

# 방화벽 활성화 (비대화형)
echo "y" | ufw enable

log_info "방화벽 상태:"
ufw status

#=============================================================================
# 4. Nginx 설정
#=============================================================================
log_info "Nginx 설정 중..."

# 기본 설정 백업
if [ -f /etc/nginx/sites-enabled/default ]; then
    mv /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/default.bak
fi

log_info "Nginx 설정 파일을 /etc/nginx/sites-available/에 복사하세요."
log_info "예: sudo cp nginx.conf /etc/nginx/sites-available/soundroutine"
log_info "    sudo ln -s /etc/nginx/sites-available/soundroutine /etc/nginx/sites-enabled/"

#=============================================================================
# 5. Let's Encrypt SSL 인증서 발급
#=============================================================================
log_info "SSL 인증서를 발급하려면 다음 명령을 실행하세요:"
echo ""
echo "  sudo certbot --nginx -d your-domain.com"
echo ""
echo "자동 갱신 확인:"
echo "  sudo certbot renew --dry-run"
echo ""

#=============================================================================
# 6. 시스템 서비스 활성화
#=============================================================================
systemctl enable nginx
systemctl start nginx

log_info "Nginx 상태:"
systemctl status nginx --no-pager

#=============================================================================
# 7. 완료 메시지
#=============================================================================
echo ""
echo "=============================================="
log_info "VPS 설정이 완료되었습니다!"
echo "=============================================="
echo ""
echo "다음 단계:"
echo "1. 도메인 DNS A 레코드를 이 VPS IP로 설정하세요."
echo "2. Nginx 설정 파일에서 'your-domain.com'을 실제 도메인으로 변경하세요."
echo "3. SSL 인증서를 발급하세요: sudo certbot --nginx -d your-domain.com"
echo "4. 내부망에서 autossh를 실행하여 터널을 형성하세요."
echo ""
echo "터널 테스트 명령:"
echo "  # 내부망에서 실행"
echo "  ssh -R 8080:localhost:8000 user@vps-ip"
echo ""
