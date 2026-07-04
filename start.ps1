# ARIA — Voice/Realtime Customer Support Agent
# One-command startup for Windows PowerShell

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   ARIA — AI Realtime Intelligence Agent  ║" -ForegroundColor Cyan
Write-Host "  ║   Powered by Google Gemini API           ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check .env
$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $rootDir ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "  ⚠️  No .env file found!" -ForegroundColor Yellow
    Write-Host "  Create one from .env.example and add your GEMINI_API_KEY" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Quick setup:" -ForegroundColor White
    Write-Host "    Copy-Item .env.example .env" -ForegroundColor Gray
    Write-Host "    notepad .env" -ForegroundColor Gray
    Write-Host ""
    $continue = Read-Host "  Continue anyway? (y/N)"
    if ($continue -ne "y") { exit 1 }
}

# Install Python deps
Write-Host "  📦 Installing Python dependencies..." -ForegroundColor Blue
pip install -r requirements.txt -q

# Install Node deps
Write-Host "  📦 Installing Node dependencies..." -ForegroundColor Blue
Set-Location (Join-Path $rootDir "frontend")
npm install --silent
Set-Location $rootDir

Write-Host ""
Write-Host "  🚀 Starting servers..." -ForegroundColor Green
Write-Host "     Backend  → http://localhost:8000" -ForegroundColor White
Write-Host "     Frontend → http://localhost:5173" -ForegroundColor White
Write-Host "     API Docs → http://localhost:8000/docs" -ForegroundColor White
Write-Host ""

# Start backend in background
Start-Process powershell -WorkingDirectory $rootDir -ArgumentList "-NoExit", "-Command", "python -m uvicorn backend.main:app --reload --port 8000" -WindowStyle Normal

# Small delay then start frontend
Start-Sleep -Seconds 2
Set-Location (Join-Path $rootDir "frontend")
npm run dev
