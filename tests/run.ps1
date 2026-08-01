$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  python -m unittest discover -s tests -p "test_*.py"
  [scriptblock]::Create((Get-Content -LiteralPath "scripts/local-ai-client.ps1" -Raw)) | Out-Null
  Get-ChildItem opencode -Filter *.json | ForEach-Object {
    Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json | Out-Null
  }
  Get-Content -LiteralPath vendor.lock.json -Raw | ConvertFrom-Json | Out-Null
  Write-Output "[ok] Windows-side checks passed"
} finally {
  Pop-Location
}
