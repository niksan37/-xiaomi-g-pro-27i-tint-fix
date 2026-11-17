# Installs the Xiaomi G Pro 27i tint-fix watcher for the current user (no admin rights needed).
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = 'Stop'

$src = Join-Path $PSScriptRoot 'tintfix.pyw'
$dst = Join-Path $env:LOCALAPPDATA 'XiaomiTintFix'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

# Locate pythonw.exe next to the Python interpreter (python.exe, else the py launcher).
$pyw = $null
foreach ($launcher in @(@('python'), @('py', '-3'))) {
    $exe = $launcher[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $extra = @()
    if ($launcher.Count -gt 1) { $extra = $launcher[1..($launcher.Count - 1)] }
    try {
        $candidate = & $exe @extra -c "import os, sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))" 2>$null
    } catch { $candidate = $null }
    if ($candidate -and (Test-Path $candidate)) { $pyw = $candidate; break }
}
if (-not $pyw) {
    Write-Host 'Python 3 was not found. Install it from https://www.python.org/downloads/ and run this script again.'
    exit 1
}

# Stop a running watcher, copy the script, register autostart, start it.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*XiaomiTintFix*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
Start-Sleep -Seconds 1

New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item $src -Destination $dst -Force
$script = Join-Path $dst 'tintfix.pyw'
Set-ItemProperty -Path $runKey -Name 'XiaomiTintFix' -Value ('"{0}" "{1}" --boot' -f $pyw, $script)
# Mark the entry as enabled, as Task Manager does. Without this value, recent Windows 11 builds
# skipped the entry at logon (observed on 25H2: only entries marked 0x02 here were started).
$approved = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
if (-not (Test-Path $approved)) { New-Item -Path $approved -Force | Out-Null }
New-ItemProperty -Path $approved -Name 'XiaomiTintFix' -PropertyType Binary -Force `
    -Value ([byte[]](0x02, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)) | Out-Null
Start-Process -FilePath $pyw -ArgumentList ('"{0}"' -f $script) -WorkingDirectory $dst

Write-Host "Installed to $dst"
Write-Host 'The watcher is running and will start at every logon.'
Write-Host 'Manual trigger: Ctrl+Alt+F10.  Log file: tintfix.log in the folder above.'
