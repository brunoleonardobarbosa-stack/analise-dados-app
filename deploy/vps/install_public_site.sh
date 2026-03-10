#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/analise-dados-app"
SERVICE_NAME="engclinica"

if [[ "$EUID" -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/vps/install_public_site.sh"
  exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "Diretorio $APP_DIR nao encontrado."
  echo "Copie o projeto para esse caminho antes de executar."
  exit 1
fi

cd "$APP_DIR"

apt update
apt install -y python3 python3-venv python3-pip nginx

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

cp deploy/vps/engclinica.service /etc/systemd/system/${SERVICE_NAME}.service
cp deploy/vps/nginx-engclinica.conf /etc/nginx/sites-available/${SERVICE_NAME}
ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/${SERVICE_NAME}

if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

systemctl daemon-reload
systemctl enable --now ${SERVICE_NAME}
nginx -t
systemctl restart nginx

if command -v ufw >/dev/null 2>&1; then
  ufw allow 22 || true
  ufw allow 80 || true
fi

echo "Deploy publico concluido."
echo "URL: http://$(curl -s ifconfig.me || echo '<IP_DA_VPS>')"
echo "Status app: systemctl status ${SERVICE_NAME} --no-pager"
