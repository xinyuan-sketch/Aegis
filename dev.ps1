# Aegis dev launcher (Windows 11 / PowerShell)
#   .\dev.ps1          first run auto-bootstraps, then starts (hot reload on)
#   .\dev.ps1 -Reset   drop & rebuild DB, then start
#   .\dev.ps1 -Check   run self-check only, do not start
param([switch]$Reset, [switch]$Check)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. venv
if (-not (Test-Path venv)) {
    Write-Host "[1/5] Creating virtualenv..." -ForegroundColor Cyan
    python -m venv venv
}
$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

# 2. deps (marker file avoids reinstalling every run; reinstalls if requirements changed)
$marker = "venv\.deps-installed"
$needDeps = -not (Test-Path $marker)
if (-not $needDeps) {
    if ((Get-Item requirements.txt).LastWriteTime -gt (Get-Item $marker).LastWriteTime) { $needDeps = $true }
}
if ($needDeps) {
    Write-Host "[2/5] Installing dependencies..." -ForegroundColor Cyan
    & $py -m pip install -q --upgrade pip
    & $py -m pip install -q -r requirements.txt
    New-Item $marker -ItemType File -Force | Out-Null
}

# 3. .env (auto-generate random keys if missing)
if (-not (Test-Path .env)) {
    Write-Host "[3/5] Generating .env and keys..." -ForegroundColor Cyan
    $secret = & $py -c "import secrets;print(secrets.token_urlsafe(48))"
    $master = & $py -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
    @(
        "AEGIS_SECRET_KEY=$secret",
        "AEGIS_MASTER_KEY=$master",
        "AEGIS_DATABASE_URI=sqlite:///aegis.db",
        "AEGIS_ENV=development"
    ) | Set-Content -Encoding ascii .env
}

# 4. database —— 先 migrate 建表/补列（幂等），再建默认管理员（存在则跳过）
if ($Reset -and (Test-Path aegis.db)) { Remove-Item aegis.db* -Force }
Write-Host "[4/5] Syncing database schema..." -ForegroundColor Cyan
& $py cli.py migrate
& $py cli.py seed-tools
& $py cli.py create-admin admin admin123   # 幂等：已存在则跳过，不会重置密码

# self-check
& $py check.py
if ($LASTEXITCODE -ne 0) { Write-Host "Self-check failed, aborting." -ForegroundColor Red; exit 1 }
if ($Check) { exit 0 }

# 5. run (debug hot reload: edits to .py / templates take effect without restart)
Write-Host "[5/5] Starting http://127.0.0.1:5000  (Ctrl+C to stop)" -ForegroundColor Green
& $py run.py
