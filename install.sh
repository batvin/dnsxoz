#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Server Optimization & DNS Test Panel — installer (v2.1)
# Tested on: Ubuntu 20.04/22.04/24.04, Debian 11/12
# Usage (as root):
#   curl -fsSL https://raw.githubusercontent.com/batvin/dnsxoz/main/install.sh | bash
# ---------------------------------------------------------------------------
set -e

REPO_RAW_BASE="https://raw.githubusercontent.com/batvin/dnsxoz/main"
INSTALL_DIR="/opt/server-panel"
SERVICE_NAME="server-panel"
PANEL_PORT="${PANEL_PORT:-8088}"
PIP_BIN=""

# Common PyPI mirrors (tried in order if official fails)
PIP_MIRRORS=(
  "https://pypi.org/simple/|pypi.org"
  "https://pypi.tuna.tsinghua.edu.cn/simple/|pypi.tuna.tsinghua.edu.cn"
  "https://mirrors.aliyun.com/pypi/simple/|mirrors.aliyun.com"
  "https://pypi.mirrors.ustc.edu.cn/simple/|pypi.mirrors.ustc.edu.cn"
  "https://mirrors.cloud.tencent.com/pypi/simple/|mirrors.cloud.tencent.com"
  "https://mirrors.huaweicloud.com/repository/pypi/simple/|mirrors.huaweicloud.com"
  "https://mirrors.bfsu.edu.cn/pypi/web/simple/|mirrors.bfsu.edu.cn"
)

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

echo "==> ساخت virtualenv..."
python3 -m venv "${INSTALL_DIR}/venv"
PIP_BIN="${INSTALL_DIR}/venv/bin/pip"

configure_pip_mirror() {
  local index_url="$1"
  local host="$2"
  "$PIP_BIN" config set global.index-url "$index_url" >/dev/null
  "$PIP_BIN" config set global.trusted-host "$host" >/dev/null
  "$PIP_BIN" config set global.timeout 1000 >/dev/null
  echo "    pip mirror: $index_url"
}

try_pip_install() {
  local req_file="$1"
  local last_err=""
  for entry in "${PIP_MIRRORS[@]}"; do
    local url="${entry%%|*}"
    local host="${entry##*|}"
    echo "==> تلاش نصب با میرور: $url"
    configure_pip_mirror "$url" "$host" || true
    if "$PIP_BIN" install --upgrade pip >/dev/null 2>/tmp/panel-pip-err.log \
      && "$PIP_BIN" install -r "$req_file" 2>/tmp/panel-pip-err.log; then
      echo "    ✅ نصب موفق با $url"
      return 0
    fi
    last_err="$(tail -5 /tmp/panel-pip-err.log 2>/dev/null || true)"
    echo "    ❌ ناموفق — میرور بعدی..."
  done
  echo "خطا: نصب pip از همه میرورها شکست خورد."
  echo "$last_err"
  return 1
}

echo "==> نصب پکیج‌های پایتون (با fallback میرور)..."
try_pip_install "${INSTALL_DIR}/requirements.txt"

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

SERVER_IP=$(curl -fsSL ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

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
