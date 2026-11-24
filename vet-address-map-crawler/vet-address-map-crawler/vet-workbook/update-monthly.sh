#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ $# -ne 1 ]]; then echo '用法：bash update-monthly.sh 專案ID'; exit 2; fi
mkdir -p "${VET_DATA_DIR:-data}/schedule-logs"
log="${VET_DATA_DIR:-data}/schedule-logs/$(date +%Y%m%d-%H%M%S)-$1.log"
.venv/bin/python -m vetapp.cli update "$1" 2>&1 | tee -a "$log"
