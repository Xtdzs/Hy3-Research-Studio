<div align="center">

# Hy3 Research Studio

**AI 原生科研与创作工作台 · Powered by [Tencent Hy3](https://github.com/Tencent-Hunyuan/Hy3)**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

*腾讯犀牛鸟开源人才培养计划 · Build a vibe-coded application powered by Hy3 参赛作品*

[🌐 English](README.en.md) | [🇨🇳 中文](README.md)

</div>

---

## 📹 功能演示

以下演示视频覆盖全部 11 个功能模块，点击封面图即可观看（将在 GitHub 内置播放器中打开）。

---

### 🔬 深度研究（Deep Research）— 3分41秒

> 旗舰功能演示：输入研究主题 → 8阶段自动化流水线（规划→检索→压缩→假设→证据图谱→研究空白→实验设计→报告）→ SSE实时进度条 → 流式生成带 [sN] 引用的学术报告 → 点击引用查看原文 → 多标签页查看证据包/假设/证据图谱/研究空白/实验设计 → 章节级润色

<video src="docs/videos/deep-research.mp4" poster="docs/videos/thumbs/deep-research.jpg" controls width="100%"></video>

---

### 🔍 智能检索（Smart Search）— 2分01秒

> 多源学术检索演示：跨 OpenAlex/Crossref/arXiv 并行检索 → Hy3 自动优化检索式（中文→英文）→ LLM 语义过滤 → 论文卡片列表展示 → 一键收藏到文献库 → 流式生成带引用的结构化检索简报 → 按年份/类型/开放获取过滤

[<img src="docs/videos/thumbs/smart-search.jpg" alt="🔍 智能检索演示" width="100%">](docs/videos/smart-search.mp4)

---

### 💡 思路提炼（Idea Refiner）— 2分11秒

> Agent 模式演示：研究教练对话 → 强制先检索再回答（tool_choice 强制调用检索工具）→ 显示"正在检索真实文献"气泡 → 两层过滤（关键词+语义）→ 带 [rN] 引用的回答流式输出 → Hy3 自动生成2-4个引导下一步的选择题 → 多轮收敛机制

[<img src="docs/videos/thumbs/idea-refiner.jpg" alt="💡 思路提炼演示" width="100%">](docs/videos/idea-refiner.mp4)

---

### 📄 论文研讨 & ✍️ 写作工坊（Paper Seminar & Writing Studio）— 1分50秒

> **论文研讨**：PDF 上传解析 → 基于全文对话（总结贡献/分析局限/提取大纲）→ 多轮对话带完整论文上下文 → 上传历史保存
>
> **写作工坊**：4种写作工具（摘要生成/大纲生成/段落扩写/综述撰写）→ 输入要点 → 流式输出 → 历史可查

[<img src="docs/videos/thumbs/paper-writing.jpg" alt="📄✍️ 论文研讨 & 写作工坊演示" width="100%">]([docs/videos/paper-writing.mp4](https://github.com/user-attachments/assets/832bbb26-2db6-4dfd-9945-ae912c036186))
![demo_video](https://github.com/user-attachments/assets/832bbb26-2db6-4dfd-9945-ae912c036186)

---

### 🔨 创造工坊（Feature Workshop）— 1分25秒

> ⚠️ 概念验证（PoC）演示：功能市场4个官方模板卡片（科研/审稿/会议/医学）→ AI Quick Build 一句话创建功能（输入描述 → Hy3 生成名称/emoji/系统Prompt/布局/引导语）→ 独立工作空间 + 专属布局（会议双栏布局）→ 引导语气泡 → 退出/重入状态管理

[<img src="docs/videos/thumbs/feature-workshop.jpg" alt="🔨 创造工坊演示" width="100%">](docs/videos/feature-workshop.mp4)

---

### 📚 文献库 / 📊 反馈看板 / 🕐 历史记录 / 👤 个人主页 / ⚙️ 设置 — 1分53秒

> **📚 文献库**：跨模块收藏论文、文件夹分类、笔记、跨会话持久化
>
> **📊 反馈看板**：提交反馈、词云可视化、投票机制、按票数排序
>
> **🕐 历史记录**：跨模块统一活动历史，按模块过滤，可恢复上次会话
>
> **👤 个人主页**：身份/机构/研究兴趣设置，个性化画像驱动"猜你想搜"
>
> **⚙️ 设置**：API Key 管理、检索源开关、默认偏好、模型连接状态、数据管理

[<img src="docs/videos/thumbs/history-settings.jpg" alt="📚📊🕐👤⚙️ 文库/反馈/历史/设置演示" width="100%">](docs/videos/history-settings.mp4)

---

## 项目简介

Hy3 Research Studio 是一个以**研究工作流**为中心、由腾讯 Hy3 大模型驱动的端到端科研与创作工作台。它不仅能聊天、写报告，更能将模糊的研究想法自动转化为可执行的研究计划，通过多源学术检索、证据压缩、假设生成、研究空白挖掘、验证实验设计，最终输出带引用溯源的长篇学术报告。

**无需 Node.js、无需数据库、无需 Docker。** 仅需 Python 3.10+ 和一个 Hy3 API Key。

---

## ⚠️ 项目状态说明

| 模块 | 完成度 | 说明 |
|------|--------|------|
| 🔬 深度研究 | ✅ **完整可用** | 8 阶段流水线全链路对接 Hy3，SSE 流式输出 |
| 🔍 智能检索 | ✅ **完整可用** | 多源检索 + Hy3 检索式优化 + 语义过滤 + 流式简报 |
| 💡 思路提炼 | ✅ **完整可用** | Agent + Tool Calling，强制先检索再回答，带引用 |
| 📄 论文研讨 | ✅ **基本可用** | PDF 上传 + 基于全文对话 |
| ✍️ 写作工坊 | ✅ **基本可用** | 摘要/大纲/段落/综述工具 |
| 🔨 创造工坊 | ⚠️ **概念验证 / 初步开发** | 详见下方说明 |
| 📚 文献库 / 📊 反馈 / 🕐 历史 / 👤 个人 / ⚙️ 设置 | ✅ **完整可用** | 基础功能完善 |

### 🔨 关于「创造工坊」的特别说明

创造工坊（Feature Workshop）是本项目提出的一个**前瞻性概念**：让用户通过一句话或可视化拖拽创建拥有独立界面、专属布局、AI 能力的微应用（AI Native Feature），而非仅仅保存 Prompt。

**当前状态**：
- ✅ AI Quick Build（一句话生成）功能可用：输入描述后 Hy3 可生成名称、emoji、系统 Prompt、布局类型和引导语，生成的功能在通用聊天布局下可以正常使用（带自定义系统 Prompt 的对话）
- ✅ 4 个官方模板（Research / Review / Meeting / Medical）的 UI 布局 HTML 结构完整
- ✅ 功能市场（收藏 / 评分 / Fork / 分类浏览）数据层完整
- ⚠️ 6 种专用布局（科研三栏/审稿/会议/医学/实验/编程）目前为**前端硬编码模拟数据**，尚未真正将各功能的 system prompt 注入到专用布局的 AI 交互中
- ⚠️ Visual Builder（可视化拖拽设计器）具备完整 UI 框架和基础拖拽能力，但组件属性编辑、嵌套布局、组件连接等高级交互**尚未完成**
- ⚠️ 部分前端专用布局调用了不存在的 API 端点（`/api/chat`），专用布局下的 AI 对话暂未对接正确后端

**开发难度说明**：创造工坊的完整实现需要解决「自然语言 → 组件树 → 数据流 → AI 交互逻辑」的自动生成问题，涉及低代码引擎设计、组件 schema 抽象、AI 生成 UI 的约束校验等，是一个高难度的长期方向。当前版本作为概念验证（PoC）展示了产品形态和交互设计思路，后续迭代方向包括：统一组件 schema、将专用布局迁移到通用组件渲染引擎、完善 Visual Builder 的组件属性面板与实时预览、实现功能导出/分享/安装等。

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- 现代浏览器（Chrome / Edge / Firefox）
- Hy3 API Key（腾讯 TokenHub 或任意兼容 OpenAI 接口的服务商）

### 三步启动

```bash
# 1. 克隆仓库
git clone https://github.com/Xtdzs/Hy3-Research-Studio.git
cd "Hy3 Research Studio"

# 2. 安装依赖（仅 7 个包，无需 Node.js）
pip install -r requirements.txt

# 3. 配置 API Key
# Windows PowerShell:
Copy-Item .env.example .env; notepad .env
# macOS / Linux:
# cp .env.example .env && nano .env
```

在 `.env` 中填入你的 API Key：

```env
HY3_API_KEY=sk-your-key-here
HY3_BASE_URL=https://tokenhub.tencentmaas.com/v1
HY3_MODEL=hy3
```

启动服务：

```bash
python run.py
```

浏览器打开 **http://localhost:8731** 即可使用。所有数据（研究任务/文库/功能/设置）自动持久化在 `data/` 目录的 JSON 文件中，重启不丢失。

---

## 🧩 功能模块详解

### 1. 🔬 深度研究（Deep Research）— 核心旗舰

这是系统最核心的端到端功能。输入一个研究主题，Hy3 编排 **8 阶段自动化研究流水线**：

| 阶段 | 说明 |
|------|------|
| ① 研究规划 | Hy3 将主题拆解为 2-5 个子问题，生成英文检索式，规划报告大纲 |
| ② 多源检索 | 跨 OpenAlex / Crossref / arXiv 并行检索，关键词过滤 + LLM 语义相关性判断 |
| ③ 证据压缩 | 将原始文献摘要压缩为结构化证据包（结论/方法/局限/支撑文献），压缩比 5:1~10:1 |
| ④ 假设生成 | 基于证据推导 3-5 条可证伪研究假设，标注置信度与依据 |
| ⑤ 证据图谱 | 识别证据间的逻辑关系（支持/矛盾/延伸/特化） |
| ⑥ 研究空白 | 从证据局限挖掘未被覆盖的研究方向 |
| ⑦ 实验设计 | 为假设设计验证实验（方法/数据集/指标/基线/预期结果） |
| ⑧ 报告生成 | 按大纲逐章流式输出，关键结论带 `[sN]` 引用可点击溯源 |

**关键特性**：
- SSE 实时进度条，8 个阶段实时可见
- 流式打字机效果输出报告章节
- 点击 `[sN]` 引用右侧滑出原文信息面板
- 支持章节级润色：扩写/缩写/改风格/加引用/驳论写作
- 多标签页查看证据包、假设、证据图谱、研究空白、实验设计
- 可配置深度（快速/标准/深度）、目标引用数、风格（学术/技术/科普）、语言

### 2. 🔍 智能检索（Smart Search）

- 同时检索 OpenAlex、Crossref、arXiv（Semantic Scholar 可选增强）
- Hy3 自动优化检索式（中文→英文改写，提取核心关键词）
- LLM 语义过滤剔除无关结果
- 流式生成带引用的结构化检索简报
- 一键收藏到文献库
- 支持按年份、文献类型、开放获取过滤

### 3. 💡 思路提炼（Idea Refiner）— Agent 模式

基于 **Agent + Function Calling** 的研究教练：
- **强制先检索再回答**：通过 `tool_choice` 强制 Hy3 调用 `retrieve_papers` 工具，杜绝凭空编造
- **智能判断**：简单寒暄跳过检索，研究问题自动触发搜索
- **中文查询优化**：检测到中文自动改写为 2-5 个英文核心词，首次无结果自动重试
- **两层过滤**：关键词规则过滤 + LLM 语义过滤，无关文献在进入上下文前即被丢弃
- 回答带 `[rN]` 引用，点击可看原文
- **收敛机制**：3 轮以上对话注入收敛提示，引导形成可执行方案
- 每轮回答后 Hy3 自动生成 2-4 个引导下一步的选择题
- 支持「生成指南」将多轮讨论收敛为结构化研究框架

### 4. 📄 论文研讨（Paper Seminar）

- 通过 pypdf 解析 PDF 全文
- 基于论文内容回答问题（方法论/贡献/结果/局限）
- 自动提取大纲、核心创新点、实验结果
- 多轮对话带完整论文上下文
- 上传历史自动保存

### 5. ✍️ 写作工坊（Writing Studio）

提供多种写作辅助工具：
- 摘要生成：从要点提炼学术摘要
- 大纲生成：为论文/基金申请书生成结构化大纲
- 段落扩写：从要点展开为完整段落
- 综述撰写：带引用的文献综述
- 所有任务流式输出，历史可查

### 6. 🔨 创造工坊（Feature Workshop）— ⚠️ 概念验证

> 见上方 [项目状态说明](#-项目状态说明)。当前为 PoC 阶段。

**已实现**：
- **AI Quick Build**：一句话生成功能（名称/emoji/Prompt/布局/引导语），通用聊天布局下可正常对话
- **功能市场**：4 个精选官方模板（科研/审稿/会议/医学），卡片式浏览
- **社区交互**：1-5 星加权评分、Fork/Remix、收藏、使用计数、10 个分类
- **独立工作空间路由**：每个功能有独立 URL（`#/feature/{id}`），退出/重进状态管理稳定

**待完善（概念阶段）**：
- 6 种专用布局的 AI 交互对接（当前为模拟数据）
- Visual Builder 组件属性编辑与真实渲染
- 功能导出/分享/安装机制

两种创建模式：
- ⚡ **AI Quick Build**：一句话描述，Hy3 30秒生成（零门槛，当前可用）
- 🎨 **Visual Builder**：多轮对话→AI生成组件布局→拖拽编辑（UI 框架完整，交互待完善）

### 7-11. 文献库 / 反馈看板 / 历史记录 / 个人主页 / 设置

- **📚 文献库**：跨模块收藏论文、文件夹分类、笔记、跨会话持久化
- **📊 反馈看板**：提交反馈、词云可视化、投票机制、按票数排序
- **🕐 历史记录**：跨模块统一活动历史，按模块过滤，可恢复上次会话
- **👤 个人主页**：身份/机构/研究兴趣设置，两层个性化画像（即时信号+稳定兴趣）驱动"猜你想搜"
- **⚙️ 设置**：API Key 管理、检索源开关、默认偏好、模型连接状态、数据管理

---

## 🏗️ 系统架构

```
┌────────────────────────────────────────────────────────────┐
│                  Frontend (Vanilla JS SPA)                 │
│  Zero-build · SSE streaming · Hash routing · Dark theme    │
│  ┌──────┬──────┬───────┬───────┬────────┬─────────────────┐│
│  │ Deep │Smart │ Paper │Writing│ Idea   │  AI Feature     ││
│  │Research│Search│Seminar│Studio │Refiner │  Workshop     ││
│  └──────┴──────┴───────┴───────┴────────┴─────────────────┘│
└──────────────────────────┬─────────────────────────────────┘
                           │ SSE + REST JSON
┌──────────────────────────┴─────────────────────────────────┐
│                   FastAPI Backend                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ 8-Stage     │  │ Retrieval    │  │ Feature Store      │ │
│  │ Pipeline    │◄─┤ Tool + RAG   │  │ (CRUD + Heuristic) │ │
│  └──────┬──────┘  └──────┬───────┘  └─────────┬──────────┘ │
│         │                │                     │           │
│  ┌──────┴──────┐  ┌──────┴───────┐  ┌─────────┴──────────┐ │
│  │ Prompt Eng  │  │ Multi-Source │  │ JSON File Store    │ │
│  │ 30+templates│  │ Search Layer │  │ (零数据库)          │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────┘ │
│         └────────────┬───┘                                 │
│                      ▼                                     │
│              ┌──────────────┐                              │
│              │  Hy3 Client  │  OpenAI-compatible API       │
│              │ stream/JSON/ │  + Function Calling          │
│              │ tool_calls   │                              │
│              └──────┬───────┘                              │
└─────────────────────┼──────────────────────────────────────┘
                      │ HTTPS
              ┌───────▼────────┐
              │   Hy3 API      │  Tencent TokenHub
              └────────────────┘

  Parallel: OpenAlex · Crossref · arXiv · Semantic Scholar
```

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | 原生 HTML/CSS/JS | 零构建，零 Node 依赖，FastAPI 直接静态托管 |
| 后端 | Python 3.10+ / FastAPI / Uvicorn | 异步 SSE 流式响应 |
| AI | 腾讯 Hy3 API（OpenAI 兼容） | 全程 API 调用，无训练/微调/本地部署 |
| 检索 | OpenAlex + Crossref + arXiv | 免 Key 开箱即用，Semantic Scholar 可选 |
| 文档 | pypdf | PDF 文本提取 |
| 存储 | JSON 文件 | `data/` 目录持久化，零数据库依赖 |
| 并发 | ThreadPoolExecutor + threading.Lock | 多源并行检索 + 线程安全写操作 |

---

## 🧠 Hy3 在系统中承担的角色

Hy3 作为贯穿全系统的推理引擎，承担了 16 种角色：

| 角色 | 模块 | 具体任务 |
|------|------|----------|
| Research Planner | 深度研究 | 拆解子问题、生成检索式、规划报告大纲 |
| Search Query Optimizer | 检索/Advisor | 中文→英文检索式改写、核心词提取 |
| Evidence Compressor | 深度研究 | 将文献摘要压缩为结构化证据包（5:1+） |
| Hypothesis Generator | 深度研究 | 推导可证伪假设，标注置信度 |
| Evidence Graph Builder | 深度研究 | 识别证据间逻辑关系 |
| Gap Finder | 深度研究 | 挖掘研究空白 |
| Experiment Designer | 深度研究 | 设计验证实验方案 |
| Report Writer | 深度研究/智能检索 | 逐章流式生成长文报告 |
| Refiner | 深度研究 | 章节扩写/缩写/改风格/补引用 |
| Relevance Judge | 检索模块 | LLM 语义过滤，逐篇判断相关性 |
| Research Coach | 思路提炼 | 多轮对话引导研究方向，强制检索+引用 |
| Paper Analyst | 论文研讨 | 回答论文问题、提取大纲/创新点 |
| Feature Generator | 创造工坊 | 一句话→AI 微应用配置 |
| Feature Designer | 创造工坊 | 多轮对话生成组件布局（PoC） |
| Suggestion Engine | 首页/猜你想搜 | 基于两层画像生成检索建议 |
| LLM-as-Judge | 评测模块 | 评估证据覆盖率与关键点召回 |

---

## 📁 项目结构

```
Hy3 Research Studio/
├── backend/                    # 后端（FastAPI）
│   ├── main.py                 # API 路由入口（SSE + REST，40+ 端点）
│   ├── config.py               # 全局配置，.env 加载
│   ├── hy3_client.py           # Hy3 客户端封装（stream/JSON/tool_calls）
│   ├── pipeline.py             # 深度研究 8 阶段流水线
│   ├── models.py               # Pydantic 数据模型
│   ├── prompts.py              # 30+ Prompt 模板
│   ├── retrieval_tool.py       # Agent 检索工具（Function Calling）
│   ├── search.py               # OpenAlex/Crossref/arXiv 多源检索
│   ├── store.py                # JSON 持久化（任务/文库/历史/设置）
│   ├── features.py             # 创造工坊数据层（CRUD/模板/启发式布局）
│   └── feedback.py             # 反馈看板数据层
├── frontend/                   # 前端（零构建 SPA）
│   ├── index.html              # SPA 主页面（所有视图）
│   ├── app.js                  # 前端逻辑（路由/SSE/工作区）
│   └── styles.css              # 深色主题样式
├── data/                       # JSON 数据持久化（自动生成）
├── docs/                       # 文档与素材
│   ├── videos/                 # 功能演示视频
│   ├── 技术报告.md              # 完整技术报告
│   ├── 视频录制脚本与字幕表.md   # 视频 storyboard + SRT
│   └── 创造工坊方案.md          # 创造工坊产品方案
├── tests/                      # 测试与评测
│   ├── test_features.py        # 创造工坊单元测试
│   ├── test_offline.py         # 离线模式测试（无需 API Key）
│   ├── evaluate.py             # 三系统对比评测框架
│   └── benchmark_tasks.json    # 评测基准任务集
├── requirements.txt            # Python 依赖（7 个包）
├── .env.example                # 配置模板
├── run.py                      # 一键启动脚本
├── LICENSE                     # MIT 许可证
├── README.md                   # 本文件（中文）
└── README.en.md                # English README
```

---

## 📊 评测体系

项目提供可运行的对比评测脚本，对比三套系统：

| 系统 | 描述 |
|------|------|
| `baseline_A` | Direct Chat：直接让模型写综述，无检索 |
| `baseline_B` | Search + Single-pass：检索后把原始摘要一次性喂给模型（无压缩） |
| `studio` | 完整 Hy3 Research Studio 8 阶段流水线 |

```bash
python -m tests.evaluate --quick    # 快速评测（2 个任务）
python -m tests.evaluate            # 完整评测
python -m tests.test_offline        # 离线单元测试（无需 API Key）
```

评测指标：
- **效率**：总 Token 消耗、端到端耗时、TTFP/TTFE/TTFR/TTR 时序
- **压缩**：证据压缩比（压缩前后字符比）
- **质量**：证据覆盖率（LLM-as-judge 判定关键点召回率）

---

## ⚙️ 配置项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HY3_API_KEY` | （空） | **必填**，Hy3 API 密钥 |
| `HY3_BASE_URL` | `https://tokenhub.tencentmaas.com/v1` | API 端点（OpenAI 兼容格式） |
| `HY3_MODEL` | `hy3` | 模型名称 |
| `HY3_TIMEOUT` | `120` | 请求超时（秒） |
| `DEFAULT_SOURCES` | `openalex,crossref,arxiv` | 默认检索源 |
| `MAX_SOURCES_PER_QUERY` | `6` | 每条检索式最大返回数 |
| `HTTP_TIMEOUT` | `20` | 检索请求超时（秒） |
| `S2_API_KEY` | （空） | 可选，Semantic Scholar Key 增强召回 |
| `PORT` | `8731` | 服务端口 |

---

## 🤝 CodeBuddy 协作说明

本项目在 **CodeBuddy + Hy3** 协作下完成，体验良好，能有效提高开发效率。

---

## 📝 注意事项

- 本项目**全程通过 API 调用 Hy3**，不进行任何训练/微调/本地推理部署
- 检索依赖 OpenAlex / Crossref / arXiv 公共 API，网络不可用时界面可正常浏览，AI 功能有离线兜底提示
- 所有数据存储在 `data/` 目录的 JSON 文件中，可随时备份或删除重置
- 未配置 `HY3_API_KEY` 时系统进入离线模式：创造工坊使用启发式布局推断，其他 AI 功能提示配置 Key
- 创造工坊专用布局当前为概念验证阶段，专用布局 AI 交互使用模拟数据，详见 [项目状态说明](#-项目状态说明)

---

## 📄 许可证

MIT License

---

<div align="center">

**Built with [Tencent Hy3](https://github.com/Tencent-Hunyuan/Hy3) · CodeBuddy Assisted**

提交至 [Tencent-Hunyuan/Hy3](https://github.com/Tencent-Hunyuan/Hy3) `rhinobird2026` 分支 · v0.0.1

</div>
