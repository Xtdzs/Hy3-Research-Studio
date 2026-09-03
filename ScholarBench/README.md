<div align="center">

# ScholarBench

**面向学术研究与创作工作流的端到端评测基准 · Powered by [Tencent Hy3](https://github.com/Tencent-Hunyuan/Hy3-preview)**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Dataset](https://img.shields.io/badge/Dataset-v0.1-green)]()

*腾讯犀牛鸟开源人才培养计划 · 实战任务一（Hy3-preview application with custom evaluation rubric）*

</div>

---

## 这是什么

ScholarBench 是一个**面向学术研究与创作工作流的多任务评测基准**。它不只是"给某个应用打分"，而是回答三个问题：

1. **学术工作流该评什么** —— 8 个任务族 T1–T8，覆盖从检索、综述、开题、论文问答、引用核对到学术写作与 Agent 工具链
2. **怎么评才可信** —— 客观规则指标 + 7 维横切 Rubric，凡能确定性计算的绝不交给模型
3. **被测系统站在哪** —— 8 维能力画像 + 难度分层曲线，直接刻画能力边界

任何学术助手、Deep Research 系统或 Agent 框架，只要实现一个 `generate(task)` 接口（约 50 行）即可接入，产出可横向对比的 Leaderboard。

**本仓库与被测应用 `Hy3-Research-Studio` 平级、解耦** —— `scholarbench/` 目录可独立复制到任何地方使用，不依赖被测应用。

---

## 快速开始

```bash
cd ScholarBench
pip install -r requirements.txt
cp .env.example .env        # 填入 HY3_API_KEY

# 1) 构建数据集（仅用种子库 + 本地 gold 池快照，无需联网）
python -m scholarbench build_dataset

# 2) 离线冒烟：验证「数据集 → 指标 → 报告」链路（零 API 成本）
python -m scholarbench run --split lite --systems mock --no-judge
python -m scholarbench report --results results/results.jsonl --out eval_results

# 3) 真实评测（被测系统为 Hy3 Research Studio）
python -m scholarbench run --split lite --systems studio

# 4) 只看某一族 / 某几道题（控制积分消耗）
python -m scholarbench run --families T5 --systems studio
python -m scholarbench run --tasks T5-021,T5-022 --systems studio
```

---

## 任务族设计（T1–T8）

| ID | 任务族 | 核心能力 | 客观指标（规则，零 LLM） | 条数 |
|----|--------|---------|------------------------|------|
| **T1** | 文献综述生成 | 检索 · 压缩 · 结构化生成 | Recall@key_points、引用可解析率、结构要素覆盖率 | 8 |
| **T2** | 研究开题与实验设计 | 压缩 · 结构化生成 | 关键点召回、实验要素覆盖、假设可证伪性 | 8 |
| **T3** | 学术检索与相关性筛选 | 检索召回 | **Precision@10 / Recall@20 / nDCG@10** | 8 |
| **T4** | 论文深度问答 | 长文理解 · 引用溯源 | 答案 F1、**证据句命中率** | 8 |
| **T5** | 引用核对与事实核查 | 引用溯源 · 安全合规 | **三分类 Accuracy / 宏 F1 / 伪造引用检出率** | 28 |
| **T6** | 学术写作 | 长文理解 · 结构化生成 | ROUGE-L、大纲 schema 合法性、长度一致性 | 8 |
| **T7** | 研究思路 Agent 多轮对话 | 检索 · 工具调用 · 多轮 | 工具调用准确率、引用率、收敛性 | 8 |
| **T8** | 多步工具工作流 | 工具调用 · 多轮 | 工具链 F1、产物要素覆盖 | 8 |

**难度梯度** easy : medium : hard = 2 : 3 : 3（每族）。hard 样本刻意选取模型易失败类型：2025 年后的新方向、需要**否定性结论**、多跳对比、证据冲突、引用易被伪造的主题。

**T5 是本基准最容易规模化的部分**：正负样本由程序化构造（真实引用 → 交叉错配 → 标题改写伪造），可零标注成本地持续扩充。

---

## 指标体系

### 两层结构

```
TaskScore(T_i) = α_i · Objective_i + (1 - α_i) · Rubric_i      # α 按任务可调
BenchScore     = Σ w_i · TaskScore(T_i)   （按已评测族归一化）
Capability(C_j)= 依赖 C_j 的任务族得分均值  → 8 维能力画像
```

新增（v0.1.1，依据 [CorrectFaith] / [LITERAS] / [DeepResearchEval]）：

- **T1 引用一致性**：正文 `[sN]` 标记 ↔ 文末参考文献条目的双向解析覆盖率
- **T5 分组诊断**：报告按样本构造分组给出准确率——`cross_pair` 分组即
  **引用忠实度探针**（论断配真实但无关文献，应判 unrelated），
  `mutated_title` 分组即**伪造引用检出率**
- **分块评测**：`--chunked` 将长文按标题/段落切块逐段评分（[DeepResearchEval] 页级思想）

α（客观指标权重）按族设定：T3/T5 = 0.85、T4/T8 = 0.70、T7 = 0.60、T1/T6 = 0.45、T2 = 0.35。
**原则：凡是能被规则判定的任务，就以规则判定为主**，LLM 只评规则算不出来的部分。这既降低 judge 方差，也把 API 成本压到最低。

### 横切 Rubric（7 维，对全部任务族生效）

| 维度 | 权重 | 判什么 |
|------|------|--------|
| D1 事实准确性 | 25% | 论断与证据一致，无无源断言 / 幻觉 |
| D2 证据可追溯性 | 20% | 引用真实、指向支撑论断的具体文献 |
| D3 专业术语正确性 | 10% | 术语准确，无生造 / 误用 / 堆砌 |
| D4 覆盖与完整性 | 15% | 关键点召回、结构要素齐全 |
| D5 逻辑与结构 | 10% | 无跳步 / 循环论证 / 自相矛盾 |
| D6 安全合规 | 10% | 无越界建议、必要免责、无 PII |
| D7 用户可理解性 | 10% | 信噪比、篇幅效率（抗注水） |

每维有 1/3/5 分行为锚点，judge 必须输出 `score + 扣分理由 + 原文引文片段`。**单次调用输出全部 7 维**，成本约为分次调用的 1/7。任务族可通过 `RUBRIC_OVERRIDES` 调整权重（如 T5 把 D1 提到 0.35）。

---

## 接入你自己的系统

```python
# scholarbench/adapters/my_system.py
from scholarbench.adapters.base import SUT
from scholarbench.schema import Answer, Task

class MySystem(SUT):
    name = "my_system"
    def generate(self, task: Task) -> Answer:
        text = my_pipeline(task.prompt)          # 你的系统
        return Answer(task_id=task.task_id, system=self.name,
                      content=text, citations=[], meta={})
```

### 方式二：HTTP 端点（推荐，跨语言）

你的服务只要暴露一个 `POST` 端点：

```http
POST /api/bench/generate
Content-Type: application/json

{"task": {"task_id":"T5-001","family":"T5","prompt":"请核查以下论断…","context":{...}}}
```

```json
{
  "content": "{\"verdict\": \"supported\", \"reason\": \"摘要直接支撑该论断\"}",
  "citations": [{"marker":"[s1]","title":"Attention Is All You Need",
                 "doi":"10.48550/arXiv.1706.03762","year":2017}],
  "tool_calls": [{"name":"search","args":{"query":"..."},"result":"2 hits"}],
  "meta": {"agent": "my-agent/1.0"}
}
```

只有 `content` 必填，其余可选。评测命令：

```bash
python -m scholarbench run --systems http:http://localhost:8000/api/bench/generate --split lite --timeout 300
```

### 方式三：命令行程序（不限语言）

协议：task JSON 走 **stdin**，程序向 stdout 打印 **最后一行** Answer JSON（前面的日志会被忽略）。

```bash
python -m scholarbench run --systems "cli:python examples/agent_cli_stub.py" --split lite
# 也支持 Node / Go / Shell
python -m scholarbench run --systems "cli:node my_agent.js" --split lite
```

### 开箱可用的样板

| 文件 | 说明 |
|------|------|
| [`examples/agent_server_stub.py`](examples/agent_server_stub.py) | FastAPI 端点样板，`uvicorn examples.agent_server_stub:app --port 8000` |
| [`examples/agent_cli_stub.py`](examples/agent_cli_stub.py) | stdin/stdout 样板，任意语言照此实现即可 |

需要鉴权 / 定制请求头时，用环境变量：

| 变量 | 作用 |
|------|------|
| `SB_AGENT_TOKEN` | 以 `Authorization: Bearer <token>` 发送 |
| `SB_AGENT_HEADERS` | 额外请求头，JSON 字符串，如 `'{"X-Team":"foo"}'` |
| `SB_AGENT_TIMEOUT` | 单次请求超时（秒），HTTP 默认 300、CLI 默认 600 |

### 内置 adapter 一览

| spec | 用途 |
|------|------|
| `studio` / `studio:/abs/path` | Hy3 Research Studio（内部直连 8 阶段流水线 / 检索 / 论文问答） |
| `openai_compat:model` | 任意 OpenAI 兼容端点（裸模型对照下界） |
| `http:http://host/path` | 任意已部署的 Web 应用（跨语言、跨机器） |
| `cli:python my_agent.py` | 命令行程序（task 走 stdin，answer 走 stdout） |
| `human:annotator_A` | 人工作答，产出**人类基线上界锚点** |
| `mock` | 确定性假回答，用于离线冒烟与 CI |

> **T5 判定的兼容口径**：三分类 `verdict` 支持三种输出形态统一计分 —— `meta.verdict` / 回答 JSON 里的 `verdict` 字段 / 裸词开头（`supported`）。不同接入方式不会因格式差异被误判。

> 为什么要有 `human`：Leaderboard 若只有模型互相比，读者无法判断"60 分算好还是差"。用 human adapter 标注 20%–30% 样本，就得到绝对参照系。

---

## 长跑稳定性与断点续跑

长批评测（跨多个系统 / 外部端点慢 / 网络抖动）常以小时计。以下机制保证**中断后不必从头再来**：

| 参数 | 默认 | 作用 |
|------|------|------|
| `--timeout` | 300s（CLI） | 单次生成超时上限；thinking 模型慢就调大，如 `--timeout 600` |
| `--retries` | 2 | 单条失败自动重试，指数退避（1s→2s→4s，上限 8s） |
| `--no-thinking` | off | 关闭思考链：hy3/hy4/deepseek 单题约 50x 提速、省 token，且减少撞 429 限流；glm 等强制思考模型自动忽略 |
| `--parallel` | 1 | 并发生成 worker 数。**TokenHub 网关容量有限，并行 >3 极易触发 429**，默认串行 |
| `--rate-interval` | 0 | 两次模型请求的最小间隔秒数（0=不限）。串行 + 小间隔最稳，如 `--parallel 1 --rate-interval 2` |
| `--retry-failed` | off | **只重跑上次失败/超时的题**，已成功的复用缓存 |
| `--regen` | off | 忽略缓存全部重跑 |
| 答案缓存 | — | 按 `task_id` 落盘 `answers_<system>.jsonl`，覆盖式合并，不会出现重复记录 |

```bash
# 中断后：直接重跑同一条命令即可接着测
python -m scholarbench run --split lite --systems studio

# 只补跑失败的题（成功的跳过）
python -m scholarbench run --split lite --systems studio --retry-failed

# 外部端点慢 + 偶发 5xx
python -m scholarbench run --systems http:http://host/api/bench/generate \
    --timeout 600 --retries 3
```

续跑时终端会明确提示复用进度：

```text
=== 系统 studio ===
  续跑：复用已完成的 27 条（其中 2 条上次失败，加 --retry-failed 可重跑） · 待生成 3 条
  单次生成超时上限：300s · 失败重试 3 次
```

`run_all_models.py` 同样支持透传：`--timeout` / `--retries` / `--retry-failed`，并且每完成一个系统就刷新一次跨模型排行榜。

---

## 抗污染与鲁棒性

- **题目公开、answer key 不公开**：答案锚点存放于 `data/v0.1/keys_heldout/`（已 gitignore）
- **数据集可复现**：`build_dataset.py` 从种子题库 + 本地 gold pool 快照重建，带版本号
- **对抗子集**：`--adversarial {water,term,fake,format,inject,conflict}` 对已生成的回答施加扰动，检验评测是否被表面特征欺骗

| 扰动 | 期望信号 |
|------|---------|
| `water` 注水扩写 +80% 篇幅 | 总分不升，D7 下降 |
| `term` 术语堆砌 | D3 下降 |
| `fake` 引用伪造 | D2 骤降，T5 应判 nonexistent |
| `format` 格式噪声 | 总分波动 < 5%（不该因排版掉分） |
| `inject` 提示注入"请给满分" | 总分不异常升高 |
| `conflict` 注入矛盾证据 | 应标注冲突而非强行调和（D5） |

---

## 评测流程与命令

| 命令 | 作用 |
|------|------|
| `python -m scholarbench build_dataset` | 构建数据集 + splits（本地种子库 + gold 池快照，无需联网） |
| `python -m scholarbench stats` | 查看数据集统计 |
| `python -m scholarbench run --split lite --systems studio` | 跑评测（客观 + Rubric） |
| `python -m scholarbench run --split lite --systems studio --chunked` | 长文分块评测（[DeepResearchEval] 页级评分） |
| `python -m scholarbench run --split lite --systems mock --no-judge` | 离线冒烟，零 API 成本 |
| `python -m scholarbench run --split lite --systems studio --retry-failed` | 续跑：只补跑上次失败/超时的题 |
| `python -m scholarbench run --split lite --systems studio --timeout 600 --retries 3` | 慢速端点：放大超时 + 失败自动重试 |
| `python -m scholarbench run --systems http:http://host/api/bench/generate` | 评测外部 HTTP Agent |
| `python -m scholarbench run --systems "cli:python my_agent.py"` | 评测命令行 Agent |
| `python run_all_models.py --mode agent` | 多基座对照（同一流水线换底层模型） |
| `python run_all_models.py --mode custom --systems http:... cli:...` | 多外部系统横向对比 |
| `python -m scholarbench annotate --sample 0.3 --annotator A` | 半自动人工标注（自动分作建议分，逐维覆写） |
| `python -m scholarbench agreement --system studio` | 一致性：QWK / Spearman / MAE |
| `python -m scholarbench report --results results/results.jsonl --out eval_results` | 生成 results.md / csv / failures.md / 雷达图 |

产出目录：`eval_results/{results.md, results.csv, failures.md, attribution.md, capability_*.png}`。

### 终端实时进度

长批评测（如 `run_all_models.py` 跨 4 个基座跑 T3/T5/T6/T7/T8）耗时可能以小时计。评测过程**在终端直接展示实时进度**，无需额外工具：

```text
========== studio_hy4 (基座: hy4-preview) ==========
  并发生成 60 条（workers=3）
  [1/60] T3-001 1420 字
  [2/60] T3-002 976 字
  ...
  生成完成 60/60（失败 0）
  评分中 36/60 (60%) · 失败 0 · 实时 BenchScore 95.1        ← 单行实时刷新
  ...
  BenchScore = 96.88  (样本 60，失败 0)
  [当前排行榜] studio_hy4 96.88 | studio_glm 96.51 | studio_ds 95.05 | studio 93.80
                                     ← 每完成一个系统刷新跨模型对比（T3 纯检索不计分，权重口径见根 README）
```

- **生成阶段**：每完成一条任务立即打印 `[i/N] 任务ID 字数`，可实时看到进展
- **评分阶段**：单行（`\r` 覆盖刷新）显示 `已评分 i/N · 失败数 · 实时 BenchScore`，分数随评分逐条上升
- **跨模型**：`run_all_models.py` 每跑完一个系统，打印一次当前全部已收集结果的排行榜，方便长跑中随时对照

---

## Hy3 在评测中承担的角色

| 角色 | 位置 | 任务 |
|------|------|------|
| **Judge** | `metrics/judge.py` | 单次调用输出 7 维 Rubric 评分 + 扣分理由 + 引文 |
| **被测对象** | `adapters/studio.py` | T1–T8 全部由 Hy3 驱动的流水线生成 |
| **Citation Verifier** | `adapters/studio.py::_run_citation_verify` | T5 的三分类引用核查 |
| **Report Writer** | `adapters/studio.py::_run_workflow` | T8 多步检索结果整合 |

全程通过 API 调用 Hy3-preview，**不进行任何训练、微调或本地推理部署**。

---

## 目录结构

```
ScholarBench/
├── scholarbench/               # 可独立复制使用的核心包
│   ├── schema.py               # Task / Answer / EvalResult 数据契约
│   ├── dataset.py              # 数据加载、splits、held-out keys
│   ├── seedbank.py             # 人工撰写的种子题库
│   ├── build_dataset.py        # 数据集构建（可复现）
│   ├── run.py                  # 评测主入口
│   ├── annotate.py             # 半自动人工标注 CLI
│   ├── agreement.py            # QWK / Spearman / MAE（纯标准库）
│   ├── attribution.py          # 9 类失败归因
│   ├── adversarial.py          # 6 类对抗扰动
│   ├── report.py               # 报告生成
│   ├── adapters/               # studio / openai_compat / http / cli / human / mock
│   └── metrics/                # objective（规则）· rubric（7 维）· judge · aggregate
├── data/v0.1/                  # 数据集（题目公开，keys 不公开）
├── leaderboard/                # 结果收录
├── SCHEMA.md                   # 数据契约规格
├── CONTRIBUTING.md             # 如何加任务 / 加 adapter / 提交结果
└── licenses.md                 # 数据来源与许可
```

---

## 局限与后续工作

- **同源模型偏差**：judge 与被测系统都基于 Hy3，存在自评偏高风险。缓解手段是客观指标占主要权重（T3/T5 α=0.85）、judge 强制给出扣分引文、并用人工标注校准（见 `agreement.py` 的 bias 字段）。
- **T4 依赖语料**：运行 `scholarbench/download_papers.py` 准备评测语料即可复现；语料文件不随仓库分发（`download_papers.py` 注释中注明来源与许可）。
- **T3 gold 池是"被引次数近似"**：以本地快照中被引次数 Top-12 作为高相关近似，非人工标注的严格 gold。
- **创造工坊为 PoC**：T8 当前只评测检索工具链，不覆盖未完成的低代码能力。

后续：扩充 Full 集至 200 条、增加多语言（EN）子集、引入跨模型 Leaderboard、把 human 基线固化进榜单。

---

## 相关学术工作（References）

ScholarBench 的设计逐点引用下列前沿研究；方法映射与引用说明见
课题目录配套文档 [`设计方案.md`](../设计方案.md)。

**应用侧（Hy3 Research Studio）**

| 引用键 | 论文 | 我们如何引用 |
|--------|------|-------------|
| LITERAS | Gorenshtein et al. LITERAS: Biomedical literature review and citation retrieval agents. *Comput. Biol. Med.*, 2025 | 深度研究 8 阶段流水线（多 Agent 综述 + 引用检索）；引用一致性指标 |
| LLM+MAS | Generation of Scientific Literature Surveys Based on LLM and MAS. *NLPCC*, 2024 | 角色分工（解析→分析→生成→整合）；自动+人工双轨评测 |
| AutoLitRec | Herrouz et al. An Autonomous Multi-Agent System for Customized Scientific Literature Recommendation. *ISI*, 2023 | 检索→过滤→推荐流水线；用户反馈→半自动标注 |
| MARVEL | Mukund et al. MARVEL: A Multi-Agent-based Research Validator and Enabler using LLMs. 2026 | 论断验证思想；工具链指标 |
| FactCheck | The Perils and Promises of Fact-Checking with LLMs. *Frontiers in AI*, 2024 | T5 引用核对的三分类决策 + 检索增强核查 |
| ContextCite | Cohen-Wang et al. ContextCite: Attributing Model Generation to Context. *NeurIPS*, 2024 | D2 证据可追溯性的归因依据 |
| HowCite | How Do LLMs Cite? — A Mechanistic Interpretation of Attribution in RAG. *ECIR*, 2026 | 失败归因的深层解释（浅层共指启发式） |

**评测侧（ScholarBench）**

| 引用键 | 论文 | 我们如何引用 |
|--------|------|-------------|
| DeepResearchEval | Tuohetiyaer et al. Deep-Research Eval: An Automated Framework for Assessing Quality and Reliability in Long-Form Reports. *Applied Sciences*, 2026 | 长文分块评测（`--chunked`）、参考库验证、能力剖面 |
| LLMJudgeSurvey | Nadăș. Large language models as judges: recent advances in LLM-based evaluation… *Artif. Intell. Rev.*, 2026 | 7 维 rubric prompting、偏差控制（长度/位置/自我偏好） |
| CorrectFaith | Wallat et al. Correctness is not Faithfulness in RAG Attributions. *ICTIR*, 2025 | D2 拆"正确性/忠实度"；T5 分组诊断（cross_pair 忠实度探针） |
| SelfCheckGPT | Manakul et al. SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection. *EMNLP*, 2023 | D1 事实准确性的零资源幻觉检测依据（Roadmap P1） |

> 完整引用格式见 [`设计方案.md` §7.1]。

- 本项目为**腾讯犀牛鸟开源人才培养计划实战任务作品**，与腾讯官方无隶属关系。
- 全程通过 API 调用 Hy3-preview，未进行任何训练 / 微调 / 本地推理部署。
- **严禁硬编码密钥**：所有密钥通过 `.env` 或环境变量注入，`.env` 已加入 `.gitignore`，提交前请执行 `git grep -n "sk-"` 自查。

## 许可证

MIT License · 数据来源与许可见 [licenses.md](licenses.md)
