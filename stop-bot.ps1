$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Processes = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*$ProjectDir*bot.py*" }

if (!$Processes) {
    Write-Host "Bot is not running."
    exit 0
}

foreach ($Process in $Processes) {
    Stop-Process -Id $Process.ProcessId -Force
    Write-Host "Stopped bot process $($Process.ProcessId)."
}
