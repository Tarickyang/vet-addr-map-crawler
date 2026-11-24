# 上傳 GitHub

建議 repository 名稱：`vet-visit-planner`。

## 網頁上傳

1. 解壓ZIP。
2. 登入GitHub，選 New repository，建議第一次先設 Private。
3. 選 uploading an existing file，或 Add file → Upload files。
4. 將 `vet-workbook` 內的檔案與資料夾拖入，讓README.md位於repository根目錄。不要只上傳ZIP。
5. 輸入提交說明並 Commit changes。`.github`、`.gitignore` 等隱藏檔較適合使用下方Git方式一併推送。

## Git／WSL

先在GitHub建立空白repository，再於解壓後的目錄執行（替換你的帳號）：

```bash
cd vet-workbook
git init
git add .
git commit -m "Initial export: veterinary visit planner"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/vet-visit-planner.git
git push -u origin main
```

登入依GitHub提示使用憑證管理工具；不要把存取權杖寫進程式或remote URL。

## 展示與執行

GitHub可閱讀程式、文件與介面截圖；上傳原始碼不等於部署服務。此FastAPI應用不能直接靠GitHub Pages執行。請依README在WSL安裝、啟動，瀏覽器開啟 http://localhost:8765。

本包未附正式Google試算表、Drive檔案識別碼、個人生日或人工業務備注。examples為既有公開院所示範快照，非即時名單。新增實際客戶資料後不要提交data/或備份。尚未替權利人選定開源授權；如要允許他人修改散布，請由專案擁有人選擇授權，第三方資料與套件仍依其原授權。
