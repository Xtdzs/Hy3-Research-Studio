# ============================================================
# Hy3 Research Studio 启动脚本（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File start.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# 0) .env 检查：缺失则提示从 .env.example 创建
if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "[警告] 未找到 .env，请先执行：" -ForegroundColor Yellow
    Write-Host "  Copy-Item .env.example .env; notepad .env"
    Write-Host "  并在 .env 中填入 HY3_API_KEY 后重新运行本脚本。"
    Write-Host ""
    exit 1
}

# 1) 依赖检查（缺则安装）
Write-Host "[1/2] 检查依赖 ..."
python -c "import fastapi, uvicorn, openai, pypdf" 2>$null
if ($LASTEXITCODE -ne 0) {
    pip install -r requirements.txt
}

# 2) 启动服务
Write-Host "[2/2] 启动 http://localhost:8731 （Ctrl+C 停止）..."
python run.py
