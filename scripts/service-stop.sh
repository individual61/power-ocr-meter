#!/usr/bin/env bash

# Stop the daemon, to be run before running in interactive mode

set -euo pipefail
sudo systemctl stop power-ocr-meter.service
sudo systemctl status power-ocr-meter.service --no-pager -l || true