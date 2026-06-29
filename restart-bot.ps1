$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $ProjectDir "stop-bot.ps1")
Start-Sleep -Seconds 1
& (Join-Path $ProjectDir "start-bot.ps1")
