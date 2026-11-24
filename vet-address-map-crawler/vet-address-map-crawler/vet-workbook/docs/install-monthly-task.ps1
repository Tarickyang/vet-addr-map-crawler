param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$ProjectId,
  [Parameter(Mandatory=$true)][ValidatePattern('^/[A-Za-z0-9_./-]+$')][string]$LinuxInstallPath,
  [ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Distro = 'Ubuntu-24.04'
)
$taskName = "VetWorkbook-$ProjectId"
$taskCommand = "wsl.exe -d $Distro -- bash $LinuxInstallPath/update-monthly.sh $ProjectId"
& schtasks.exe /Create /SC MONTHLY /D 1 /ST 08:00 /TN $taskName /TR $taskCommand /F
if ($LASTEXITCODE -ne 0) { throw '工作排程建立失敗，請查看 schtasks 回應。' }
Write-Host "已建立 $taskName，每月 1 日 08:00（Windows 當地時區）。"
Write-Host '請在工作排程器手動試跑一次，並檢查 data/schedule-logs；電腦關機時不執行。'
