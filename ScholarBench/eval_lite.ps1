# ============================================================
# ScholarBench 一键评测（Windows PowerShell）
# 前置：1) Hy3-Research-Studio 已配置 .env（含 HY3_API_KEY）
#       2) 应用已启动（python run.py → http://localhost:8731）
# 用法：powershell -ExecutionPolicy Bypass -File eval_lite.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host ""
Write-Host "==================== ScholarBench Lite 一键评测 ===================="
Write-Host ""

# 0) 数据自检（缺数据则离线重建）
Write-Host "[0/4] 数据检查 ..."
python -m scholarbench stats | Out-Null 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m scholarbench build_dataset --offline
}

# 1) 冒烟：客观指标（零 judge 成本）
Write-Host "[1/4] 客观指标冒烟（studio, Lite）..."
python -m scholarbench run --split lite --systems studio --no-judge --out results
if ($LASTEXITCODE -ne 0) { Write-Host "  失败：请确认 HY3_API_KEY 已配置" -ForegroundColor Red; exit 1 }

# 2) T5 引用核对试点（含 Rubric judge，先小批量验证）
Write-Host "[2/4] T5 引用核对试点（含 Rubric judge）..."
python -m scholarbench run --tasks T5-001,T5-002,T5-003 --systems studio --out results

# 3) Lite 全量完整评测（客观 + Rubric）
Write-Host "[3/4] Lite 全量完整评测 ..."
python -m scholarbench run --split lite --systems studio --chunked --out results

# 4) 生成报告
Write-Host "[4/4] 生成报告 → eval_results/ ..."
python -m scholarbench report --results results/results.jsonl --out eval_results

Write-Host ""
Write-Host "完成。报告位置：eval_results/results.md"
Write-Host "查看：notepad eval_results/results.md"
Write-Host "====================================================================="
