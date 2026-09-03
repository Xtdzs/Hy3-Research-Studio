<div align="center">

# Hy3 Research Studio · ScholarBench

**一个能用的 AI 科研工作台，加一套能评它的学术基准。**
<br/>*AI-native research workbench, plus the benchmark that measures it.*

Powered by [Tencent Hy3-preview](https://github.com/Tencent-Hunyuan/Hy3-preview)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero Database](https://img.shields.io/badge/Storage-JSON%20files-orange)](./)
[![Benchmark](https://img.shields.io/badge/ScholarBench-v0.1-blueviolet)](ScholarBench/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

*腾讯犀牛鸟开源人才培养计划 · 实战任务一（Hy3 application with custom evaluation rubric）*

[**English**](Hy3-Research-Studio/README.en.md) · [深度文档](设计方案.md) · [评测基准](ScholarBench/)

</div>

---

## 这个项目是什么

一个仓库，两件互相咬合的事：

| | 是什么 | 解决什么问题 |
|---|---|---|
| 🔬 **[Hy3-Research-Studio](Hy3-Research-Studio/)** | Hy3 驱动的 AI 科研工作台（**被测系统**） | 学术检索、深度研究、论文问答、引用核查到底能不能做得可信 |
| 📏 **[ScholarBench](ScholarBench/)** | 学术工作流端到端评测基准（**评测系统**） | "我的系统好不好"说不清 → 8 任务族 + 客观指标 + 对抗鲁棒性给出可比较的分数 |

**关键设计**：评测侧不依赖应用侧任何代码。`scholarbench/` 可以整个复制到任何机器上，评任何系统 —— 包括**你的 Agent**。

```
数字总览
  11 个应用功能模块       8 个评测任务族        7 维 Rubric
  84 道评测题            6 类对抗扰动          6 种系统接入方式
  8 维能力画像           3 档难度分层          0 数据库依赖
```

---

## 🎬 功能演示

| 模块 | 时长 | 演示要点 |
|---|---|---|
| 🔬 **深度研究**（旗舰） | 3'41" | 输入主题 → 8 阶段流水线 → SSE 实时进度 → 流式报告带 `[sN]` 引用 → 点击溯源 |
| 🔍 **智能检索** | 2'01" | 跨源并行检索 → 中文查询自动改写为英文关键词 → LLM 语义过滤 → 检索简报 |
| 💡 **思路提炼**（Agent） | 2'11" | `tool_choice` 强制先检索再回答 → `[rN]` 引用 → 自动生成引导选择题 → 多轮收敛 |
| 📄 **论文研讨** + ✍️ **写作工坊** | 1'50" | PDF 全文解析问答 · 摘要/大纲/扩写/综述四种写作工具 |
| 🔨 **创造工坊**（PoC） | 1'25" | 一句话生成 AI 微应用 · 功能市场 · 独立工作空间 |
| 📚 文献库 / 📊 反馈 / 🕐 历史 / 👤 个人 / ⚙️ 设置 | 1'53" | 收藏分类 · 词云投票 · 跨模块历史 · 个性化推荐 |

视频文件：[深度研究](https://github.com/user-attachments/assets/5fe54739-4611-4b49-a261-8179a12af1be) · [智能检索](https://github.com/user-attachments/assets/6ca03276-8752-4f93-b7e0-f4bf82507504) · [思路提炼](https://github.com/user-attachments/assets/b29348cc-0ac6-4006-8ba2-eeef08736a84) · [论文研讨&写作](https://github.com/user-attachments/assets/07329c05-f508-46f8-8fc0-f65bda8593b8) · [创造工坊](https://github.com/user-attachments/assets/95df1d62-03fa-4978-bd02-99c87024794f)

---

## 🧩 应用侧功能全景

| 模块 | 状态 | 能力要点 |
|---|---|---|
| 🔬 **深度研究** | ✅ 旗舰 | **8 阶段流水线**：研究规划 → 多源检索 → 证据压缩（5:1~10:1）→ 假设生成 → 证据图谱 → 研究空白 → 实验设计 → 流式报告。SSE 实时进度，章节级润色（扩写/缩写/改风格/加引用/驳论） |
| 🔍 **智能检索** | ✅ 完整 | Crossref + arXiv 并行检索 · Hy3 自动优化检索式（中→英）· LLM 语义过滤 · 结构化检索简报 · 年份/类型/开放获取过滤 |
| 💡 **思路提炼** | ✅ 完整 | **Agent + Function Calling**：`tool_choice` 强制检索杜绝编造 · 两层过滤（关键词+语义）· `[rN]` 引用 · 每轮生成 2-4 个引导选择题 · 3 轮后收敛提示 |
| 📄 **论文研讨** | ✅ 完整 | pypdf 解析 PDF 全文 · 基于全文的多轮问答 · 自动提取大纲/创新点/实验结果 |
| ✍️ **写作工坊** | ✅ 完整 | 摘要生成 / 大纲生成 / 段落扩写 / 综述撰写，流式输出，历史可查 |
| 🔗 **引用核对** | ✅ 端点化 | `/api/citation/verify` —— 三分类判定 `supported / unrelated / nonexistent`，供外部系统直接调用 |
| 🔨 **创造工坊** | ⚠️ PoC | AI Quick Build 可用（一句话生成微应用）· 功能市场/评分/Fork 完整 · 6 种专用布局与 Visual Builder **仍在概念阶段** |
| 📚 文献库 | ✅ 完整 | 跨模块收藏 · 文件夹分类 · 笔记 · 持久化 |
| 📊 反馈看板 | ✅ 完整 | 提交反馈 · 词云可视化 · 投票排序 |
| 🕐 历史记录 | ✅ 完整 | 跨模块统一活动流 · 按模块过滤 · 会话恢复 |
| 👤 个人主页 | ✅ 完整 | 身份/兴趣画像 → 驱动"猜你想搜" |
| ⚙️ 设置 | ✅ 完整 | API Key 管理 · 检索源开关 · 连接状态 · 数据管理 |

> 诚实标注：创造工坊为**概念验证**，其专用布局 UI 使用模拟数据，未在 Leaderboard 中体现为能力。

---

## 📐 评测侧能力全景

**8 个任务族**（权重按学术工作流重要性分配）：

| 族 | 任务 | 权重 | 客观指标 | α |
|---|---|---|---|---|
| T1 | 文献综述生成 | 0.18 | 关键点覆盖 + 引用一致性（正文↔文末双向解析） | 0.45 |
| T2 | 研究开题与实验设计 | 0.12 | 假设可证伪性 + 实验要素完整度 | 0.35 |
| T3 | 学术检索与相关性筛选 | 0.12 | P@10 / nDCG@10（对照 gold 文献池） | 0.85 |
| T4 | 论文深度问答 | 0.16 | 答案 F1 + 证据 span 命中 | 0.70 |
| T5 | 引用核对与事实核查 | 0.14 | 三分类准确率 + 伪造引用检出 | 0.85 |
| T6 | 学术写作 | 0.10 | ROUGE-L（对齐参考摘要） | 0.45 |
| T7 | 研究思路 Agent 多轮对话 | 0.10 | 关键点覆盖 + 引用可追溯 | 0.60 |
| T8 | 多步工具工作流 | 0.08 | 工具链 F1 + 必含章节 | 0.70 |

**可信度设计**：

- **客观优先**：凡能确定性计算的绝不交给模型（T3/T5 的 α=0.85）；judge 只负责无法规则化的部分，且强制给出扣分引文
- **7 维 Rubric**：事实准确性 / 证据可追溯 / 专业术语 / 覆盖完整 / 逻辑结构 / 安全合规 / 可理解性，单次调用出 7 维
- **对抗鲁棒性**：注水 / 术语堆砌 / 引用伪造 / 格式噪声 / 提示注入 / 证据冲突 —— 检验评测是否被表面特征欺骗
- **引用忠实度诊断**（[CorrectFaith]）：T5 按 `real_supported / cross_pair / mutated_title` 分组统计，区分"引用正确性"与"引用忠实度"
- **长文分块评测**（[DeepResearchEval]）：T1/T2/T6 按段落切块逐段评分，按字符数加权合并，避免整篇摊平
- **抗污染**：题目公开，**answer key 不公开**（`keys_heldout/` 已 gitignore）；gold 池随仓库固化，评测默认用快照而非实时检索
- **8 维能力画像 + 3 档难度曲线**：不只给总分，直接刻画能力边界

---

## 🏆 Leaderboard

<!-- LEADERBOARD:START -->

### Leaderboard（v0.1 · Lite · 多基座对照口径）

| 排名 | 系统 | BenchScore | T5 引用核对 | T6 写作 | T7 Agent | T8 工具链 | 样本 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `studio_hy4`（Hy3 应用流水线 · hy4-preview） | **96.88** | 99.8 | 59.85 | 83.19 | 83.48 | 60 |
| 2 | `studio_glm`（glm-5.3-flash） | 96.51 | 98.55 | 66.79 | 87.88 | 89.99 | 60 |
| 3 | `studio_ds`（deepseek-v4-flash-0731） | 95.05 | 99.18 | 49.18 | 70.50 | 74.70 | 60 |
| 4 | `studio`（Hy3 应用流水线 · hy3 默认基座） | 93.80 | 96.84 | 38.73 | 85.00 | 90.83 | 60 |

> - **计分原则**：只评 **LLM 参与**的任务族。T3 学术检索为纯工具检索（不经任何模型），**不进入总分**，仅保留为检索诊断（见各系统 `aggregate.json` 的 `family_scores`）。
> - **检索源**：评测固定 **arXiv 单源**（`DEFAULT_SOURCES=arxiv`），避免多源外部状态漂移污染结果。
> - **总分权重**：`T5=0.88 / T6=T7=T8=0.04`（按已评测族归一化；T1/T2/T4 未评测暂不参与；T3=0 不计分）。默认方法论权重见 [`scholarbench/schema.py`](ScholarBench/scholarbench/schema.py) git 历史。该口径下总分主要衡量**引用核对与事实核查（T5）**质量。
> - 四系统同为 60 样本（T5×28 + T6/T7/T8 各×8 + T3 诊断×8 · Lite 集），同一套 Hy3 应用流水线仅替换底层基座；`studio` 行即应用正式默认（hy3）成绩。
> - 此前 hy3 行的 T3 高分（74.2）来自更早批次检索源对 gold 的召回，当前 arXiv 状态下该族对四系统均为低召回 → 故不计分，避免"历史红利"污染模型对比。
> - `mock`（链路参照，确定性假回答，不代表任何模型）不参与本表排名。
<!-- LEADERBOARD:END -->

---

## ⚡ 快速开始

```bash
# 1) 配置 API Key（仅一次）
cd Hy3-Research-Studio && cp .env.example .env    # 填入 HY3_API_KEY

# 2) 启动应用（终端 1）→ 打开 http://localhost:8731
cd Hy3-Research-Studio && python run.py

# 3) 跑评测（终端 2）
cd ScholarBench
python -m scholarbench build_dataset
python -m scholarbench run --split lite --systems studio --no-judge   # 客观冒烟（零 judge 成本）
python -m scholarbench run --split lite --systems studio --chunked    # 完整评测（含 Rubric）
python -m scholarbench report --results results/results.jsonl --out eval_results
```

Windows 用户可用现成脚本：`Hy3-Research-Studio/start.ps1`、`ScholarBench/eval_lite.ps1`。

---

## 🔌 把你的 Agent 接进来

ScholarBench 不绑定任何模型或框架。**你只要实现一个端点/一个脚本/一个 Python 类**，就能和 Studio 站在同一套题上比较。

| 接入方式 | spec 写法 | 适合谁 |
|---|---|---|
| **HTTP 端点** | `http:http://localhost:8000/api/bench/generate` | 已部署的服务，任意语言/框架 |
| **CLI 程序** | `cli:"python my_agent.py"` | 本地脚本，Node/Go/Rust/Shell 都行 |
| **OpenAI 兼容** | `openai_compat:gpt-4o` | 裸模型基线（无检索、无工具的对照下界） |
| **Python SDK** | 继承 `SUT` 实现 `generate(task)` | 深度集成，约 50 行 |
| **Studio** | `studio` | 本项目应用流水线 |
| **Human** | `human:annotator_A` | 人工作答，产出**上界锚点** |

### 协议（HTTP）

```http
POST /api/bench/generate
Content-Type: application/json

{"task": {"task_id":"T5-001","family":"T5","prompt":"请核查以下论断…","context":{...}}}
```

```json
{
  "content": "{\"verdict\": \"supported\", \"reason\": \"摘要直接支撑该论断\"}",
  "citations": [{"marker":"[s1]","title":"Attention Is All You Need","doi":"10.48550/arXiv.1706.03762","year":2017}],
  "tool_calls": [{"name":"search","args":{"query":"..."},"result":"2 hits"}],
  "meta": {"agent": "my-agent/1.0"}
}
```

只需 `content` 必填，其余可选。T5 的三分类支持**三种输出形态**统一计分：`meta.verdict` / JSON 里的 `verdict` 字段 / 裸词开头。

### 命令

```bash
# 评测你的 HTTP 服务
python -m scholarbench run --systems http:http://localhost:8000/api/bench/generate --split lite --timeout 300

# 评测你的命令行程序
python -m scholarbench run --systems "cli:python examples/agent_cli_stub.py" --split lite

# 多系统横向对比（HTTP + CLI + 裸模型 + Studio 一起跑）
python run_all_models.py --mode custom \
  --systems http:http://localhost:8000/api/bench/generate cli:"python my_agent.py"
```

可直接复制的样板：[`examples/agent_server_stub.py`](ScholarBench/examples/agent_server_stub.py)（FastAPI）· [`examples/agent_cli_stub.py`](ScholarBench/examples/agent_cli_stub.py)（stdin/stdout）

需要鉴权时用环境变量：`SB_AGENT_TOKEN`（Bearer）、`SB_AGENT_HEADERS`（额外请求头 JSON）、`SB_AGENT_TIMEOUT`（超时）。

### 长跑稳定性

| 参数 | 默认 | 作用 |
|---|---|---|
| `--timeout` | 300s | 单次生成超时上限；thinking 模型慢就调大（`--timeout 600`） |
| `--retries` | 2 | 单条失败自动重试，指数退避（1s→2s→4s，上限 8s） |
| `--no-thinking` | off | 关闭思考链：hy3/hy4/deepseek 单题约 50x 提速、省 token，且减少撞限流；glm 等强制思考模型自动忽略 |
| `--parallel` | 1 | 并发生成 worker 数。TokenHub 网关容量有限，**并行 >3 极易触发 429**，默认串行 |
| `--rate-interval` | 0 | 两次模型请求的最小间隔秒数（0=不限）。串行 + 小间隔最稳，如 `--parallel 1 --rate-interval 2` |
| `--retry-failed` | off | **续跑增强**：只重跑上次失败/超时的题，已成功的复用缓存 |
| 答案缓存 | — | 按 `task_id` 落盘 `answers_<system>.jsonl`，**中断后重跑同一条命令即可接着测** |

```bash
python -m scholarbench run --split lite --systems studio --retry-failed --timeout 300 --retries 3
```

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Vanilla JS SPA · zero-build · SSE streaming) │
│  DeepResearch · SmartSearch · PaperSeminar · Writing    │
│  IdeaRefiner · CitationVerify · FeatureWorkshop         │
└───────────────────────────┬─────────────────────────────┘
                            │ SSE + REST JSON
┌───────────────────────────┴─────────────────────────────┐
│  FastAPI Backend                                        │
│  ┌────────────┐ ┌──────────────┐ ┌───────────────────┐  │
│  │ 8-Stage    │ │ Retrieval    │ │ JSON File Store   │  │
│  │ Pipeline   │◄┤ Tool + RAG   │ │ (零数据库依赖)     │  │
│  └─────┬──────┘ └──────┬───────┘ └───────────────────┘  │
│        │               │                                │
│  ┌─────┴──────┐ ┌──────┴────────┐                       │
│  │ 30+ Prompt │ │ Multi-Source  │  Crossref · arXiv     │
│  │ Templates  │ │ Search Layer  │  (+ S2 可选 Key)      │
│  └─────┬──────┘ └──────┬────────┘                       │
└────────┼───────────────┼────────────────────────────────┘
         └───────┬───────┘
                 ▼
        ┌────────────────┐        ┌──────────────────────┐
        │   Hy3 Client   │        │    ScholarBench      │
        │ stream / JSON  │◄───────┤  8 族 · 客观 + Rubric │
        │ function call  │  eval  │  对抗 · 能力画像      │
        └────────┬───────┘        └──────────────────────┘
                 ▼ HTTPS
        ┌────────────────┐
        │    Hy3 API     │  Tencent TokenHub
        └────────────────┘
```

---

## 📁 项目结构

```
.
├── Hy3-Research-Studio/        # 应用侧（被测系统）
│   ├── backend/                # FastAPI + 8 阶段流水线 + 多源检索 + 引用核查
│   ├── frontend/               # 原生 JS SPA（零构建）
│   ├── docs/                   # 技术报告
│   └── run.py
├── ScholarBench/               # 评测侧（可独立复制使用）
│   ├── scholarbench/
│   │   ├── schema.py           # Task / Answer / EvalResult 三套契约
│   │   ├── adapters/           # studio · openai_compat · http · cli · human · mock
│   │   ├── metrics/            # objective（规则）· rubric（7 维）· judge · aggregate
│   │   ├── adversarial.py      # 6 类对抗扰动
│   │   └── run.py              # 主评测入口
│   ├── examples/               # 接入样板（HTTP / CLI）
│   ├── data/v0.1/              # 数据集（题目公开，keys 不公开）
│   └── SCHEMA.md               # 数据契约规格
├── 设计方案.md                  # 学术方法映射（11 篇前沿研究的逐点落地）
```

---

## 🗺️ 路线图

- [x] 8 任务族数据集 + 客观指标 + 7 维 Rubric
- [x] 对抗鲁棒性与引用忠实度诊断
- [x] 多基座横向对照流水线
- [x] 外部 Agent 接入接口（HTTP / CLI / Python SDK）+ 长跑续跑
- [ ] 扩充 Full 集至 200 条，增加多语言（EN）子集
- [ ] `human` 基线固化进榜单（绝对参照系）
- [ ] 创造工坊专用布局对接真实 AI 交互
- [ ] 跨系统 Leaderboard（欢迎 PR 提交你的系统结果）

---

## 📜 许可证

MIT License
