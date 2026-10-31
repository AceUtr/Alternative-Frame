param([string]$ProjectDir = ".")
$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $ProjectDir
$oldBase = [Environment]::GetEnvironmentVariable("MODEL_BASE_URL", "Process")
$oldName = [Environment]::GetEnvironmentVariable("MODEL_NAME", "Process")
$oldKey  = [Environment]::GetEnvironmentVariable("MODEL_API_KEY", "Process")
try {
    if (-not (Test-Path -LiteralPath ".\run_real_two_phase_demo.py")) {
        throw "Wrong directory: run from alternative-frame/v0.1"
    }
    if (-not (Test-Path -LiteralPath ".\live_api_smoke.py")) {
        throw "Missing live_api_smoke.py: extract it from the previous test toolkit into v0.1"
    }
    $python = Join-Path (Get-Location).Path ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing .venv Python in project directory"
    }
    $env:MODEL_BASE_URL = Read-Host "MODEL_BASE_URL (OpenAI-compatible endpoint)"
    $env:MODEL_NAME = Read-Host "MODEL_NAME (model id)"
    $secret = Read-Host "MODEL_API_KEY (hidden)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try { $env:MODEL_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    Write-Host "STEP 1: Starting one low-cost real API smoke request..."
    & $python .\live_api_smoke.py
    if ($LASTEXITCODE -ne 0) {
        throw "API smoke failed. Check endpoint, model, account quota and provider compatibility."
    }
    Write-Host "Smoke succeeded. Evidence: live_api_smoke_evidence.json"
    $go = Read-Host "Run the two-phase live-agent demo? This may cost money. Type YES to proceed"
    if ($go -ceq "YES") {
        & $python .\run_real_two_phase_demo.py
        if ($LASTEXITCODE -ne 0) {
            throw "Live-agent demo exited with a failure; keep nonsecret logs and run_id."
        }
    } else {
        Write-Host "Only API connectivity verified; live-agent demo NOT executed."
    }
} finally {
    [Environment]::SetEnvironmentVariable("MODEL_API_KEY", $oldKey, "Process")
    [Environment]::SetEnvironmentVariable("MODEL_BASE_URL", $oldBase, "Process")
    [Environment]::SetEnvironmentVariable("MODEL_NAME", $oldName, "Process")
    Pop-Location
}
