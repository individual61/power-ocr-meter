#!/usr/bin/env bash

# Start or restart the OCR daemon

set -euo pipefail
sudo systemctl daemon-reload
sudo systemctl restart power-ocr-meter.service
sudo systemctl status power-ocr-meter.service --no-pager -l