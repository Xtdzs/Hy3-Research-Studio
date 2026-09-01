# ============================================================
# ScholarBench 跨模型对比评测（Windows PowerShell）
#
# 用法：
#   1) 在下方 $Models 中配置要对比的模型（OpenAI 兼容端点）
#   2) powershell -ExecutionPolicy Bypass -File eval_models.ps1
#
# 说明：
#   - 每个模型独立设置 HY3_API_KEY/BASE_URL/MODEL 环境变量后运行，
#     结果写入 results/<model>/，互不干扰
#   - 默认只跑便宜任务族（T3 检索零模型成本 / T5 / T6 / T7 / T8），
#     并 --no-judge（仅客观指标），控制积分消耗
#   - 想跑 Rubric 打分：去掉下面 -NoJudge
#   - 想加 T1/T2（深度研究，昂贵）：在 -Families 中追加
# ============================================================

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# ---------------- 配置区：要对比的模型 ----------------
# name: 展示名；base_url: OpenAI 兼容端点；key: API Key（留 $null 自动用
#       Hy3-Research-Studio/.env 的 HY3_API_KEY，即同一 TokenHub 额度）；
# model: 模型名；judge: 是否用该模型同时充当 judge
$Models = @(
    @{ Name = "hy3";                BaseUrl = "https://tokenhub.tencentmaas.com/v1";
       Key = $null;  Model = "hy3";                Judge = $true }
    @{ Name = "glm-5.3-flash";      BaseUrl = "https://tokenhub.tencentmaas.com/v1";
       Key = $null;  Model = "glm-5.3-flash";      Judge = $true }
    @{ Name = "deepseek-v4-flash";  BaseUrl = "https://tokenhub.tencentmaas.com/v1";
       Key = $null;  Model = "deepseek-v4-flash-0731"; Judge = $true }
)

$Split   = "lite"          # lite / full / hard
$Families = @("T3", "T5", "T6", "T7", "T8")   # 便宜族；T1/T2 昂贵
$NoJudge = $true            # 仅客观指标（零 judge 成本）；改 $false 开启 Rubric
$Chunked = $false           # 长文分块评测（跑 T1/T2 时建议开启）

# ---------------- 工具函数 ----------------
function Get-StudioKey {
    # 从 ../Hy3-Research-Studio/.env 读取首个 HY3_API_KEY
    $envFile = Join-Path (Split-Path $here -Parent) "Hy3-Research-Studio\.env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match "^HY3_API_KEY=(.+)$") { return $Matches[1].Trim() }
        }
    }
    return $null
}

# ---------------- 主流程 ----------------
Write-Host ""
Write-Host "=============== ScholarBench 跨模型评测 ==============="
Write-Host "任务族: $($Families -join ', ') | split: $Split | judge: $(if($NoJudge){'客观only'}else{'Rubric'})"
Write-Host ""

foreach ($m in $Models) {
    $name = $m.Name
    $key  = $m.Key
    if (-not $key) { $key = Get-StudioKey }          # Hy3 回退到 Studio .env
    if (-not $key) {
        Write-Host "[skip] $name ：未配置 API Key" -ForegroundColor Yellow
        continue
    }

    Write-Host "`n-------------------- 运行 $name --------------------"
    $env:HY3_API_KEY    = $key
    $env:HY3_BASE_URL   = $m.BaseUrl
    $env:HY3_MODEL      = $m.Model
    if ($m.Judge) { $env:JUDGE_MODEL = $m.Model } else { Remove-Item Env:JUDGE_MODEL -ErrorAction SilentlyContinue }

    $out = "results\$name"
    New-Item -ItemType Directory -Force -Path $out | Out-Null

    $cmd = "python -m scholarbench run --split $Split --families $($Families -join ',') --systems openai_compat:$($m.Model) --out $out"
    if ($NoJudge) { $cmd += " --no-judge" }
    if ($Chunked) { $cmd += " --chunked" }
    Write-Host "  > $cmd"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "  [fail] $name" -ForegroundColor Red; continue }
    Write-Host "  [ok]   $name 结果: $out/aggregate.json" -ForegroundColor Green
}

Write-Host ""
Write-Host "完成。各模型结果目录：results/<model>/aggregate.json"
Write-Host "汇总到 README：python -m scholarbench.report_leaderboard --models hy3,deepseek-chat ..."
Write-Host "========================================================="
