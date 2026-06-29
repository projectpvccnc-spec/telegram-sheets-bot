$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$Log = Join-Path $ProjectDir "bot.log"
$Err = Join-Path $ProjectDir "bot.err"

if (!(Test-Path $Python)) {
    throw "Virtual environment not found. Run: python -m venv .venv"
}

Start-Process `
    -FilePath $Python `
    -ArgumentList "bot.py" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $Log `
    -RedirectStandardError $Err

Write-Host "Bot started. Logs: $Log / $Err"
