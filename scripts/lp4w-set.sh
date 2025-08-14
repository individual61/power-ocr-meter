#!/usr/bin/env bash

# Apply the policy to the LiFePO4wered board and set it to persist.

set -euo pipefail
DELAY_MIN=3           # wait 3 minutes after VIN drops before shutdown
AUTO_BOOT=3           # only boot when VIN present (battery OK)
VIN_THRESH=4500       # mV; raise/lower if your supply/cable sags
PERSIST=1             # 1=write to flash (CFG_WRITE 0x46), 0=do not persist

echo "[lp4w-set] Applying policy..."
sudo lifepo4wered-cli set AUTO_BOOT ${AUTO_BOOT}
sudo lifepo4wered-cli set AUTO_SHDN_TIME ${DELAY_MIN}
sudo lifepo4wered-cli set VIN_THRESHOLD ${VIN_THRESH}

if [[ "${PERSIST}" == "1" ]]; then
  echo "[lp4w-set] Persisting to flash..."
  sudo lifepo4wered-cli set CFG_WRITE 0x46
fi

"${BASH_SOURCE%/*}/lp4w-dump.sh"