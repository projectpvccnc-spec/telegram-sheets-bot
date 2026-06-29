$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$JsonPath = Join-Path $ProjectDir "service-account.json"

if (!(Test-Path $JsonPath)) {
    throw "service-account.json not found in $ProjectDir"
}

$CompactJson = Get-Content -Raw -LiteralPath $JsonPath | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 20
$CompactJson | Set-Clipboard

Write-Host "GOOGLE_SERVICE_ACCOUNT_JSON copied to clipboard."
