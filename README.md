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

## 声明

- 本项目为**腾讯犀牛鸟开源人才培养计划实战任务作品**，与腾讯官方无隶属关系。
- 全程通过 API 调用 Hy3-preview，**未进行任何训练 / 微调 / 本地推理部署**。
- **严禁硬编码密钥**：所有密钥经 `.env` 注入（已 gitignore），提交前请执行 `git grep -n "sk-"` 自查。

## 许可证

MIT License
