<div align="center">

# Hy3 Research Studio · ScholarBench

**AI 原生科研与创作工作台 + 学术工作流端到端评测基准**
Powered by [Tencent Hy3-preview](https://github.com/Tencent-Hunyuan/Hy3-preview)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*腾讯犀牛鸟开源人才培养计划 · 实战任务一（Hy3-preview application with custom evaluation rubric）*

</div>

---

## 项目结构

本仓库包含两个**平行、解耦**的组件：

| 目录 | 定位 | 快速开始 |
|------|------|---------|
| [`Hy3-Research-Studio/`](Hy3-Research-Studio/) | **应用侧**：Hy3 驱动的学术研究与创作工作台（被测系统）——深度研究 8 阶段流水线、智能检索、论文研讨、写作工坊、引用核对 | `cd Hy3-Research-Studio && python run.py` |
| [`ScholarBench/`](ScholarBench/) | **评测侧**：学术工作流端到端评测基准——8 任务族 × 7 维 Rubric × 客观规则指标 × 对抗鲁棒性，可独立复用 | `cd ScholarBench && python -m scholarbench run --split lite --systems studio` |

配套文档：

| 文档 | 内容 |
|------|------|
| [`设计方案.md`](设计方案.md) | 学术方法映射版设计方案（11 篇前沿研究的逐点引用与落地映射，持续维护） |
| [`任务一实施规划.md`](任务一实施规划.md) | 实施规划（Benchmark 三层架构、四组验证实验、里程碑） |
| [`学术调研.txt`](学术调研.txt) | 前沿研究调研笔记（应用侧 6 篇 + 评测侧 5 篇） |

---

## 为什么这样做

- **应用侧回答**：Hy3 在学术工作流里能做什么、怎么做得可信（多 Agent 综述、引用溯源、事实核查）。
- **评测侧回答**：学术工作流该怎么评、怎么评才可信、能力边界在哪（客观优先 + 人工校准 + 对抗验证）。
- 每个 Rubric 维度、每项客观指标都有可引用的前沿论文背书，方案不靠自拟。

---

## 快速开始

```bash
# 1) 配置 API Key（仅需一次）
cd Hy3-Research-Studio && cp .env.example .env && $EDITOR .env   # HY3_API_KEY

# 2) 启动应用（终端 1）
cd Hy3-Research-Studio && python run.py      # 打开 http://localhost:8731

# 3) 跑评测（终端 2）
cd ScholarBench
python -m scholarbench build_dataset --offline
python -m scholarbench run --split lite --systems studio --no-judge   # 客观冒烟
python -m scholarbench run --split lite --systems studio --chunked     # 完整评测
python -m scholarbench report --results results/results.jsonl --out eval_results
```

Windows 用户可用现成脚本：`Hy3-Research-Studio/start.ps1`、`ScholarBench/eval_lite.ps1`。

---

## 关键特性

- **8 任务族** T1–T8：文献综述 / 开题实验设计 / 学术检索 / 论文问答 / 引用核对 / 学术写作 / Agent 对话 / 多步工具工作流
- **7 维 Rubric**：事实准确性、证据可追溯性、专业术语、覆盖完整、逻辑结构、安全合规、可理解性（单次调用出 7 维）
- **客观优先**：T3/T5 的 α=0.85，规则指标占主导，judge 方差与 API 成本双降
- **引用忠实度诊断**（[CorrectFaith]）：T5 分组统计 cross_pair 检出率
- **分块评测**（[DeepResearchEval]）：长文按段逐块评分
- **对抗鲁棒性**：注水 / 术语堆砌 / 引用伪造 / 格式噪声 / 提示注入 / 证据冲突
- **人类基线**：`human` adapter 产出上界锚点

---

## 评测成果（Benchmark）

> 该表由 `python -m scholarbench report_leaderboard --auto` 从 `ScholarBench/results/<model>/aggregate.json` 自动生成。
> 复现：配置好各模型 Key 后运行 `ScholarBench/eval_models.ps1`（默认只跑便宜任务族 T3/T5/T6/T7/T8，`--no-judge` 客观指标）。
> 首次评测前请先 `cd ScholarBench && python -m scholarbench build_dataset --offline`。

<!-- LEADERBOARD:START -->
### 当前结果（v0.1 · Lite · 客观指标）

| 排名 | 系统 | BenchScore | T3 检索 | T5 引用核对 | T6 写作 | T7 Agent | T8 工具链 | 样本 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `studio`（Hy3 应用流水线） | **74.3** | 74.2 | 82.9 | 38.7 | 85.0 | 90.8 | 60 |
| 2 | `mock`（链路参照） | 51.5 | 0.0 | 100.0 | 36.8 | 70.0 | 65.0 | 64 |

> - `studio` 为 Hy3 驱动的完整应用流水线（检索增强 + 证据压缩 + 引用溯源），BenchScore **74.3**（2026-09-01 实测，Hy3 API，客观指标）。
> - 短板分析：**T6 学术写作 38.7**——流水线的写作工具未对齐参考摘要（ROUGE-L 低）；**T3 检索 74.2**——OpenAlex 限流（429）导致部分 easy 样本召回下降。详见 `ScholarBench/eval_results/`。
> - `mock` 为确定性假回答，仅用于验证评测链路，**不代表任何模型**。
> - 裸模型对比（`hy3` / `hy4-preview` / `glm-5.3-flash` / `deepseek-v4-flash-0731`）结果待补：`cd ScholarBench && python run_all_models.py`（断点续跑，约 30–60 分钟）。
<!-- LEADERBOARD:END -->

### 评测设置

| 项 | 值 |
|----|----|
| 数据集 | ScholarBench v0.1（84 题，lite 64） |
| 任务族 | T1–T8（此处默认只列便宜族 T3/T5/T6/T7/T8；T1 综述 / T2 开题 / T4 论文问答成本较高，按需增跑） |
| 指标 | 客观规则指标（P@10 / nDCG@10 / 三分类准确率 / 工具链 F1 等）+ 7 维 Rubric（可选） |
| 人类基线 | `human` adapter（上界锚点，规划中） |
| 偏差控制 | 客观权重 α：T3/T5=0.85；judge 可用独立模型（`JUDGE_MODEL`） |

---

## 声明

- 本项目为**腾讯犀牛鸟开源人才培养计划实战任务作品**，与腾讯官方无隶属关系。
- 全程通过 API 调用 Hy3-preview，**未进行任何训练 / 微调 / 本地推理部署**。
- **严禁硬编码密钥**：所有密钥经 `.env` 注入（已 gitignore），提交前请执行 `git grep -n "sk-"` 自查。

## 许可证

MIT License
