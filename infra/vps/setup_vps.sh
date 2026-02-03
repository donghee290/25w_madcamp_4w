#!/bin/bash
# VPS 초기 설정 스크립트
# 새 VPS에서 root 또는 sudo 권한으로 실행

set -e

echo "=== 1. 시스템 업데이트 ==="
apt update && apt upgrade -y

echo "=== 2. Nginx 설치 ==="
apt install -y nginx

echo "=== 3. Nginx 설정 파일 생성 ==="
cat > /etc/nginx/sites-available/soundroutine << 'EOF'
server {
    listen 80;
    server_name n-e.kr;

    client_max_body_size 100M;

    # Backend API & Auth (SSH 터널로 연결)
    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend (SSH 터널로 연결)
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

echo "=== 4. Nginx 활성화 ==="
ln -sf /etc/nginx/sites-available/soundroutine /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "=== 5. 방화벽 설정 ==="
ufw allow 22
ufw allow 80
ufw allow 443
ufw --force enable

echo "=== 6. SSH 터널 수신 허용 ==="
# /etc/ssh/sshd_config에 GatewayPorts 설정 (선택)
grep -q "GatewayPorts" /etc/ssh/sshd_config || echo "GatewayPorts yes" >> /etc/ssh/sshd_config
systemctl restart sshd

echo "=== 완료 ==="
echo "VPS IP를 Cloudflare DNS에 A 레코드로 등록하세요."
echo "내부 서버에서 autossh 명령어 실행:"
echo "  autossh -M 0 -N -R 8080:localhost:8000 -o ServerAliveInterval=30 -i ~/.ssh/id_rsa root@[NEW_VPS_IP]"
