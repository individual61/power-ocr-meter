#!/usr/bin/env bash

# Show current LiFePO4wered telemetry and config

set -euo pipefail
echo "=== Telemetry ==="
lifepo4wered-cli get vin vout vbat iout
echo "=== Policy ==="
lifepo4wered-cli get AUTO_BOOT AUTO_SHDN_TIME VIN_THRESHOLD VBAT_BOOT PI_BOOT_TO PI_SHDN_TO