# Removes the Xiaomi G Pro 27i tint-fix watcher (process, autostart entry, install folder).
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1
$dst = Join-Path $env:LOCALAPPDATA 'XiaomiTintFix'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*XiaomiTintFix*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
Start-Sleep -Seconds 1

Remove-ItemProperty -Path $runKey -Name 'XiaomiTintFix' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run' `
    -Name 'XiaomiTintFix' -ErrorAction SilentlyContinue
if (Test-Path $dst) { Remove-Item -Recurse -Force -Confirm:$false $dst }

Write-Host 'Removed. The monitor itself was not changed.'
