# GitHub 匯出驗證（2026-11-24）

- 在 Linux／Python 虛擬環境成功安裝 requirements.txt。
- `python -m unittest discover -s tests -v`：14 項測試全部通過，包含合併、人工欄位保存、分組、路徑及輸出驗證。
- 四個 Shell 腳本通過 `bash -n`；前端通過 `node --check static/app.js`。
- 範例 16 筆公開院所資料的生日、人工備注及業務規則皆空白。
- 匯出排除虛擬環境、執行資料、快取及私人帳號設定。

本次測試未重新擷取正式院所名單或重跑全市道路計算，亦未實機測試 Windows WSL、手機 Maps App。原有線上測試與畫面見另附日期的 VALIDATION.md。GitHub Actions 設定已附上，尚未在 GitHub 執行。
