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

## 🧠 为什么选科研工作流（场景选择理由）

选这个场景是三重权衡的结果：

1. **高信任门槛**：科研是"一句话都假不得"的场景——幻觉、伪引用、不可追溯的断言会**直接摧毁可信度**。在别的场景能靠"大概能用"蒙混的模型缺陷，在这里会立刻暴露，是检验 LLM 应用真实能力的试金石。
2. **覆盖完整应用形态**：文献调研（检索 + 深度研究）、写作（摘要/综述/扩写）、研讨问答（多轮 QA）、研究教练（Agent 多轮对话）、工具链编排（检索→整合→报告）——一个场景同时覆盖 **Agent / 问答 / 摘要 / 分析 / 生成** 全部形态，且每个形态都对应真实的科研岗位任务。
3. **可测才可信**：科研产出天然可以构造客观判据（gold 文献池、1:1 要点对齐、引用三分类、对抗改写），同一场景下评测侧的 rubric 与客观指标都能"落地"，避免做出"可运行但不可测"的演示应用。

由此落地的 6 个真实用例：🔬 深度研究（8 阶段 Agent）、🔍 智能检索、💡 思路提炼（Agent）、📄 论文研讨、✍️ 写作工坊、🔗 引用核对——它们共同构成一个"检索 → 阅读 → 写作 → 核查"的闭环，测评结论也因此能直接映射回产品改进（见下方[评测结论](#-评测结论与模型能力边界)）。

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

**8 个任务族**（权重按学术工作流重要性分配；**只对"模型相关（LLM 参与）"族计分**，纯工具族与未评测族不进入总分）：

| 族 | 任务 | 权重 | 客观指标 | α |
|---|---|---|---|---|
| T1 | 文献综述生成 | 0.18（未评测） | 关键点覆盖 + 引用一致性（正文↔文末双向解析） | 0.45 |
| T2 | 研究开题与实验设计 | 0.12（未评测） | 假设可证伪性 + 实验要素完整度 | 0.35 |
| T3 | 学术检索与相关性筛选 | 0（纯检索·诊断） | P@10 / nDCG@10（对照 gold 文献池） | 0.85 |
| T4 | 论文深度问答 | 0.16（未评测） | 答案 F1 + 证据 span 命中 | 0.70 |
| T5 | 引用核对与事实核查 | 0.14 | 三分类准确率 + 伪造引用检出 | 0.85 |
| T6 | 学术写作 | 0.10 | ROUGE-L（对齐参考摘要） | 0.45 |
| T7 | 研究思路 Agent 多轮对话 | 0.10 | 关键点覆盖 + 引用可追溯 | 0.60 |
| T8 | 多步工具工作流 | 0.08 | 工具链 F1 + 必含章节 | 0.70 |

> 注：**T3 学术检索为纯工具检索（不经任何 LLM），不计入总分、仅保留为检索诊断**；已评测且计分的族为 T5/T6/T7/T8（权重 0.14/0.10/0.10/0.08，与全库默认比例一致）。T1/T2/T4 尚未评测，汇总只对"有任务且权重大于 0"的族归一化，补测后自动恢复。族权重对应 `schema.FAMILY_WEIGHTS`，α 对应 `schema.FAMILY_ALPHA`。

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

### Leaderboard（v0.1 · Lite · 仅模型相关族加权）

| 排名 | 系统 | BenchScore | T5 引用核对 | T6 写作 | T7 Agent | T8 工具链 | 样本 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `studio_glm`（glm-5.3-flash） | **86.82** | 98.5 | 66.8 | 87.9 | 90.0 | 60 |
| 2 | `studio_hy4`（Hy3 应用流水线 · hy4-preview） | 83.22 | 99.8 | 59.9 | 83.2 | 83.5 | 60 |
| 3 | `studio`（Hy3 应用流水线 · hy3 默认基座） | 79.04 | 96.8 | 38.7 | 85.0 | 90.8 | 60 |
| 4 | `studio_ds`（deepseek-v4-flash-0731） | 75.78 | 99.2 | 49.2 | 70.5 | 74.7 | 60 |

> - **加权原则**：只评"模型相关（LLM 参与）"族——T3 学术检索为纯工具检索（不经模型），**不计入总分、仅保留为检索诊断**（各系统 T3 诊断分见 `aggregate.json` 的 `family_scores`）。T1/T2/T4 未评测暂不参与。
> - **总分权重**：计分族 T5/T6/T7/T8 按默认方法论比例 **0.14 / 0.10 / 0.10 / 0.08** 加权，仅对有任务族归一化（分母 0.42）。
> - 四系统同为 60 样本（T3×8 诊断 + T5×28 + T6/T7/T8 各×8 · Lite 集），同一套 Hy3 应用流水线仅替换底层基座；`studio` 行即应用正式默认（hy3）成绩。
> - `mock`（链路参照，确定性假回答，不代表任何模型）不参与本表排名。

#### 轻量版复评（2026-09-03 · hy4 单系统 · T6/T7/T8 失分题 ×12）

针对归因出的 T6/T7/T8 短板优化 adapter 后（引用纪律 / 写作覆盖 / T8 整合带全文摘要）的同题复评，**非正式全量**，仅作趋势参考：

| 族 | 同题数 | hy4 优化前 | hy4 优化后 | Δ | glm（旧，同题参照） |
|---|---|---|---|---|---|
| T6 写作 | 4 | 57.6 | 55.7 | −1.9 | 69.0 |
| T7 Agent | 4 | 71.2 | 70.0 | −1.2 | 81.0 |
| T8 工具链 | 4 | 81.2 | **93.4** | **+12.3** | 95.7 |
| 合计 | 12 | 70.0 | 73.05 | +3.05 | 81.9 |

- **T8 显著改善**（四题全升、与 glm 差距收敛至 2.2 分）：整合阶段附上检索文献摘要后，内容可信度 rubric（D1/D2）大幅提升；原 `VERBOSITY` 标签在复评中消失。
- **T7 瓶颈不在 prompt**：复评答案已做到"零伪造 `[sN]` + 显式标注一般性建议"，但检索 0 命中的 hard 题无论怎么写都会被判 `UNSUPPORTED_CITATION`/`MISSED_KEY_POINT`——短板在检索召回侧（跨源查询构造、多路查询），非写作层。
- **T6 持平**：摘要类 hard 题要点覆盖未见系统性提升，待进一步研究。
- 以上为温度采样单次结果，存在波动（如 T7-008 −8）；正式结论以全量 60 样本复评为准。
<!-- LEADERBOARD:END -->

---

## 🧭 评测结论与模型能力边界

评测范围：Lite 集 60 样本 × 4 系统，同一套 Hy3 应用流水线仅替换底层基座；总分口径 = 仅模型相关族加权（T5/T6/T7/T8 · 0.14/0.10/0.10/0.08）。

**结论要点**

1. **引用核对（T5）是共同最强项**（96.8 ~ 99.8）：结构化三分类任务对基座差异不敏感，Hy3 流水线在此族无短板。
2. **学术写作（T6）是最大分水岭**（38.7 / 49.2 / 59.9 / 66.8）：摘要类 hard 题要求"要点 1:1 覆盖且不掺水"，hy3 默认基座显著弱于 glm。
3. **Agent 思路（T7）的硬伤在"检索空题时的引用纪律"**：glm 以"覆盖要点 + 标注证据缺口"兜底整体占优（87.9）；hy4 复评后已做到零伪引，但受限于检索命中。
4. **工具链（T8）基座差异最小**（74.7 ~ 90.8）：工具调用全部正确，差距全在**整合阶段有没有内容可依**——这是少数可归因、可修复的工程缺口（见下）。

**典型失败 case 归因**（错误标签定义见 `ScholarBench/SCHEMA.md`）

| 题 | 族 · 难度 | 现象（task_score） | 错误标签 | 根因归因 |
|---|---|---|---|---|
| T3-003/004 | 检索 · 中 | hy4 2.1 / glm 7.7 / ds 0.7 | `RETRIEVAL_MISS` | arXiv 检索源当批次低召回——**外部源漂移**，不计入总分仅诊断 |
| T6-006 | 写作 · hard | hy3 26.9 / ds 35.2 / hy4 37.5 / glm 55.4 | `MISSED_KEY_POINT` + `VERBOSITY` | 长摘要 1:1 要点覆盖失败：模型用自带模板重排要点；hy3 最重，写作族共性短板 |
| T6-002 | 写作 · easy | hy3 33.4 | `MISSED_KEY_POINT` + `VERBOSITY` | hy3 摘要纪律弱，easy 题同样丢分（hy4 复评后已缓解） |
| T7-006 | Agent · hard | hy4 44.0 / glm 67.0 | `UNSUPPORTED_CITATION` | 检索 0 命中仍输出具体论断；hard 题检索命中即定生死，glm 以覆盖+标注缺口兜底 |
| T7-005 | Agent · 中 | hy4 64.0 / glm 72.0 | `UNSUPPORTED_CITATION` | 同上；hy4 复评后改为显式"非文献结论"标注，零伪引但覆盖分仍受检索限制 |
| T8-002 | 工具链 · easy | hy4 79.8 | rubric 低分（无标签） | 整合阶段只送文献标题 → 事实靠内部知识补全；adapter 改带摘要后 T8 族轻量复评 **+12.3** |
| T5-022 | 引用 · hard | hy3 88.4（全系统 >85） | 对抗边界例（无标签） | 对抗 hard 表述与原论文错位——尾部边界；T5 族整体仍处 96.8+ 高位 |

**能力边界分析**

- **结构化程度越高，基座差距越小**：T5 三分类（96.8+）与 T8 工具链（74.7+）主要由流水线工程化决定，规则校验/工具调用已抹平多数基座差异；差距集中在需要**内容生成与对齐**的环节。
- **hy4 相对 glm 的剩余差距在主战场是 T6 写作**（59.9 vs 66.8）+ 部分 T7 检索空题，T8 经 adapter 优化后已收敛（轻量 +12.3，全量待复评）。
- **Agent 类任务的最深边界是"无文献也要答"**：检索 0 命中下，正确姿势 = 覆盖通用要点 + 显式标注证据缺口 + 零伪引——同时考验检索召回与表达克制，prompt 只能解一半。
- **评测侧自身边界**：T3 检索族受外部源状态影响（跨批次漂移）故**仅诊断不计分**；T1/T2/T4 尚未评测；`human` 上界基线未固化；Full 集 200 条扩展进行中（见路线图）。

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
