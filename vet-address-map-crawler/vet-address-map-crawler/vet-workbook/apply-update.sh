#!/usr/bin/env bash
# Copies this package's code only. Existing data and venv are preserved.
set -euo pipefail
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
dest="${1:-$HOME/vet-workbook}"
mkdir -p -- "$dest"
dest="$(cd -- "$dest" && pwd)"
if [[ "$src" == "$dest" ]]; then exec bash "$dest/install.sh"; fi
if [[ -e "$dest/vetapp" ]]; then
  backup="$dest/code-backups/$(date +%Y%m%d-%H%M%S)-$$"
  mkdir -p -- "$backup"
  for item in vetapp static tests examples docs requirements.txt README.md VERSION install.sh run.sh update-monthly.sh apply-update.sh; do
    if [[ -e "$dest/$item" ]]; then cp -a -- "$dest/$item" "$backup/"; fi
  done
  echo "舊程式備份：$backup（人工資料 data/ 未變更）"
fi
for item in vetapp static tests examples docs requirements.txt README.md VERSION install.sh run.sh update-monthly.sh apply-update.sh start-windows.cmd; do
  cp -a -- "$src/$item" "$dest/"
done
chmod +x "$dest/"*.sh
bash "$dest/install.sh"
echo "完成。請先停止舊程序，再執行 bash '$dest/run.sh'。"
