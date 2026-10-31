param([string]$ProjectDir = ".")
$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $ProjectDir
$oldBase = $env:MODEL_BASE_URL
$oldName = $env:MODEL_NAME
$oldKey = $env:MODEL_API_KEY
try {
    $python = Join-Path (Get-Location).Path ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { throw "Missing .venv Python" }
    if (-not (Test-Path ".\live_api_diagnose.py")) { throw "Missing live_api_diagnose.py" }
    $env:MODEL_BASE_URL = (Read-Host "MODEL_BASE_URL (https://api.deepseek.com)").Trim()
    $env:MODEL_NAME = (Read-Host "MODEL_NAME (deepseek-v4-pro)").Trim()
    $sec = Read-Host "MODEL_API_KEY (hidden)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { $env:MODEL_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    & $python .\live_api_diagnose.py
    Write-Host "Read the evidence JSON for HTTP status. Do not share credentials."
} finally {
    $env:MODEL_BASE_URL = $oldBase
    $env:MODEL_NAME = $oldName
    $env:MODEL_API_KEY = $oldKey
    Pop-Location
}
