#!/usr/bin/env bash

# Manually run in headless mode, shouldn't need this often

set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "${REPO_DIR}/power_meter_ocr_monitor.py" --no-preview --interval 5 --resolution 800x600 --log-dir logs