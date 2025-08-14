#!/usr/bin/env bash

# When logging in via NoMachine, stop the service if running, then start in interactive mode.

set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"${REPO_DIR}/scripts/service-stop.sh" || true

export LIBCAMERA_LOG_LEVELS="*:ERROR"
export OPENCV_LOG_LEVEL="ERROR"

python3 "${REPO_DIR}/power_meter_ocr_monitor.py" --interval 0.35 --resolution 800x600 --log-dir logs