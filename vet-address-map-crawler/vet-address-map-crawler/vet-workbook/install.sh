#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null; then
  echo '請先執行：sudo apt update && sudo apt install -y python3 python3-venv fonts-noto-cjk'
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3,10), "需要 Python 3.10 或更新版本（建議 Ubuntu 24.04）"'
if ! python3 -m venv .venv; then
  echo '請執行 sudo apt install -y python3-venv，再重新安裝。'
  exit 1
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
if ! fc-list 2>/dev/null | grep -qi 'Noto.*CJK'; then
  echo '尚未找到中文字型。請執行 sudo apt install -y fonts-noto-cjk，否則地圖中文可能無法顯示。'
fi
mkdir -p data
chmod 700 data
printf '\n安裝完成。執行 bash run.sh，於 Windows 瀏覽器開啟 http://localhost:8765\n'
