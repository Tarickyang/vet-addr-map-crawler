#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then echo '請先執行 bash install.sh'; exit 1; fi
exec .venv/bin/python -m uvicorn vetapp.web:app --host 127.0.0.1 --port "${VET_PORT:-8765}" --log-level info
