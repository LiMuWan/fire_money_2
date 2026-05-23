#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${FIREMONEY_APP_DIR:-/opt/firemoney}"
SERVICE_USER="${FIREMONEY_SERVICE_USER:-ubuntu}"
ENV_DIR="/etc/firemoney"
ENV_FILE="$ENV_DIR/firemoney.env"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run with sudo: sudo bash scripts/linux/install_firemoney_systemd.sh" >&2
  exit 1
fi

cd "$APP_DIR"

if ! python3 -m venv --help >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y python3-venv python3-pip
fi

install -d -m 0755 "$ENV_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  cat >"$ENV_FILE" <<EOF
FIREMONEY_APP_DIR=$APP_DIR
FIREMONEY_PYTHON=$APP_DIR/.venv/bin/python
FIREMONEY_PREVIEW_BIND=0.0.0.0
FIREMONEY_PREVIEW_PORT=8765
FIREMONEY_BETA_INTERVAL_SECONDS=60
FIREMONEY_MARKET_DATA_TIMEOUT_SECONDS=20
FIREMONEY_ALLOW_MARKET_DATA_TIMEOUT=true
FEISHU_ENABLED=false
# FEISHU_WEBHOOK_URL=
# FEISHU_WEBHOOK_SECRET=
# FEISHU_APP_ID=
# FEISHU_APP_SECRET=
# FEISHU_RECEIVE_ID=
# FEISHU_RECEIVE_ID_TYPE=chat_id
EOF
  chmod 0600 "$ENV_FILE"
  chown root:root "$ENV_FILE"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
chmod +x "$APP_DIR/scripts/linux/start_firemoney_preview.sh"
chmod +x "$APP_DIR/scripts/linux/start_firemoney_beta_watch.sh"

install -m 0644 "$APP_DIR/scripts/linux/firemoney-preview.service" /etc/systemd/system/firemoney-preview.service
install -m 0644 "$APP_DIR/scripts/linux/firemoney-beta-watch.service" /etc/systemd/system/firemoney-beta-watch.service

sed -i "s/^User=.*/User=$SERVICE_USER/" /etc/systemd/system/firemoney-preview.service
sed -i "s#^WorkingDirectory=.*#WorkingDirectory=$APP_DIR#" /etc/systemd/system/firemoney-preview.service
sed -i "s#^ExecStart=.*#ExecStart=$APP_DIR/scripts/linux/start_firemoney_preview.sh#" /etc/systemd/system/firemoney-preview.service

sed -i "s/^User=.*/User=$SERVICE_USER/" /etc/systemd/system/firemoney-beta-watch.service
sed -i "s#^WorkingDirectory=.*#WorkingDirectory=$APP_DIR#" /etc/systemd/system/firemoney-beta-watch.service
sed -i "s#^ExecStart=.*#ExecStart=$APP_DIR/scripts/linux/start_firemoney_beta_watch.sh#" /etc/systemd/system/firemoney-beta-watch.service

systemctl daemon-reload
systemctl enable firemoney-preview.service
systemctl enable firemoney-beta-watch.service

echo "Installed FireMoney systemd services."
echo "Edit $ENV_FILE before starting beta watch, especially Feishu credentials."
echo "Start preview: sudo systemctl start firemoney-preview"
echo "Start beta watch after beta-check: sudo systemctl start firemoney-beta-watch"
