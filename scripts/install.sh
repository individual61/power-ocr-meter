#!/usr/bin/env bash
set -euo pipefail

USER_NAME="paulwb"
REPO_DIR="/home/${USER_NAME}/Documents/GitHub/power-ocr-meter"
PY="/usr/bin/python3"                    # swap to venv path if you use one
INTERVAL="5"
RES="800x600"
LOG_DIR="logs"
UNIT_PATH="/etc/systemd/system/power-ocr-meter.service"

echo "[install] Installing OS packages..."
sudo apt-get update -y
sudo apt-get install -y python3-opencv python3-picamera2 git build-essential libsystemd-dev

echo "[install] Ensure user in groups (camera/i2c/gpio)"
sudo usermod -aG video,i2c,gpio "${USER_NAME}"

echo "[install] Install LiFePO4wered host tools (CLI/daemon/bindings) if missing..."
if ! command -v lifepo4wered-cli >/dev/null 2>&1 ; then
  tmp=$(mktemp -d)
  git clone https://github.com/xorbit/LiFePO4wered-Pi.git "$tmp/LiFePO4wered-Pi"
  make -C "$tmp/LiFePO4wered-Pi" all
  sudo make -C "$tmp/LiFePO4wered-Pi" user-install
fi

echo "[install] Enable lifepo4wered daemon..."
sudo systemctl enable lifepo4wered-daemon.service
sudo systemctl start  lifepo4wered-daemon.service

echo "[install] Create logs dir..."
mkdir -p "${REPO_DIR}/${LOG_DIR}"

echo "[install] Write systemd unit to ${UNIT_PATH} ..."
sudo tee "${UNIT_PATH}" >/dev/null <<UNIT
[Unit]
Description=Power OCR Meter (PiCam -> 7-seg -> CSV)
After=lifepo4wered-daemon.service

[Service]
Type=simple
User=${USER_NAME}
Group=${USER_NAME}
WorkingDirectory=${REPO_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=LIBCAMERA_LOG_LEVELS=*:ERROR
Environment=OPENCV_LOG_LEVEL=ERROR
ExecStartPre=/bin/sleep 5
ExecStart=${PY} ${REPO_DIR}/power_meter_ocr_monitor.py --no-preview --interval ${INTERVAL} --resolution ${RES} --log-dir ${LOG_DIR}
Restart=always
RestartSec=2
KillSignal=SIGTERM
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
UNIT

echo "[install] Reload & enable service..."
sudo systemctl daemon-reload
sudo systemctl enable power-ocr-meter.service
sudo systemctl restart power-ocr-meter.service

echo "[install] Done. Tail logs with: ${REPO_DIR}/scripts/logs-tail.sh"