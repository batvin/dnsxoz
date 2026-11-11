#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Server Optimization & DNS Test Panel — installer
# Tested on: Ubuntu 20.04/22.04/24.04, Debian 11/12
# Usage (as root):
#   curl -fsSL https://raw.githubusercontent.com/<YOUR_USER>/<YOUR_REPO>/main/install.sh | bash
# ---------------------------------------------------------------------------
set -e

REPO_RAW_BASE="https://raw.githubusercontent.com/<YOUR_USER>/<YOUR_REPO>/main"
INSTALL_DIR="/opt/server-panel"
SERVICE_NAME="server-panel"
PANEL_PORT="${PANEL_PORT:-8088}"

if [ "$EUID" -ne 0 ]; then
  echo "لطفا اسکریپت را با دسترسی root اجرا کنید (sudo)."
  exit 1
fi

echo "==> نصب پیش‌نیازها..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip dnsutils curl

echo "==> ساخت دایرکتوری نصب در ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}/templates"

echo "==> دانلود فایل‌های پنل از گیت‌هاب..."
curl -fsSL "${REPO_RAW_BASE}/app.py" -o "${INSTALL_DIR}/app.py"
curl -fsSL "${REPO_RAW_BASE}/requirements.txt" -o "${INSTALL_DIR}/requirements.txt"
curl -fsSL "${REPO_RAW_BASE}/templates/index.html" -o "${INSTALL_DIR}/templates/index.html"

echo "==> ساخت virtualenv و نصب پکیج‌های پایتون..."
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip >/dev/null
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "==> ساخت سرویس systemd..."
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Server Optimization & DNS Test Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Environment=PANEL_PORT=${PANEL_PORT}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/app.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}

SERVER_IP=$(curl -fsSL ifconfig.me || hostname -I | awk '{print $1}')

echo ""
echo "✅ نصب با موفقیت انجام شد!"
echo "پنل در آدرس زیر در دسترس است:"
echo "   http://${SERVER_IP}:${PANEL_PORT}"
echo ""
echo "برای مشاهده لاگ سرویس:"
echo "   journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "توجه امنیتی: این پنل هیچ احراز هویتی ندارد. پیشنهاد می‌شود:"
echo "  - پورت ${PANEL_PORT} را فقط برای IP خودتان در فایروال باز کنید، یا"
echo "  - آن را پشت nginx + Basic Auth یا یک reverse-proxy با SSL قرار دهید."
