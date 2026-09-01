# ScholarBench 数据契约（v0.1）

三套契约：**Task**（题目，公开）· **Answer**（被测系统输出）· **EvalResult**（评测结果）。
所有文件均为 UTF-8 JSONL / JSON。

---

## 1. Task（题目）

文件：`data/v0.1/T*.jsonl`，每行一个 JSON 对象。

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 唯一 ID，格式 `T<n>-<3位序号>`，如 `T5-021` |
| `family` | str | 任务族 `T1`–`T8` |
| `suite` | str | 数据集文件名前缀，如 `T5_citation` |
| `difficulty` | str | `easy` / `medium` / `hard` |
| `prompt` | str | 交给被测系统的输入 |
| `capability` | list[str] | 依赖的原子能力 `C1`–`C8` |
| `context` | object | 任务专属上下文，见下表 |
| `meta` | object | 元数据（来源、构造方式等） |

### context 各任务族约定

| 族 | context 字段 |
|----|-------------|
| T1 | `depth`: `quick` / `standard` |
| T2 | `depth` |
| T3 | `per_query`: 每条检索式抓取篇数；`top_k`: 返回上限 |
| T4 | `pdf_path`: 论文路径（相对 `data/v0.1/`）；或直接给 `paper_text` |
| T5 | `reference`: `{title, doi, year, abstract}` |
| T6 | `writing_type`: `abstract` / `outline` / `expand` / `survey`；`min_outline_items` |
| T7 | 无（单轮问题；`expected_tools` 放在 key 中） |
| T8 | `steps`: 多步检索的子查询列表 |

### 示例

```json
{
  "task_id": "T5-021",
  "family": "T5",
  "suite": "T5_citation",
  "difficulty": "hard",
  "prompt": "请核查以下论断与其被引文献的关系：\n论断：自注意力机制通过并行计算替代了循环结构…",
  "capability": ["C4", "C8"],
  "context": {
    "reference": {
      "title": "BERT: Pre-training of Deep Bidirectional Transformers Revisited",
      "doi": "10.0000/fake.3f2a9c1b7e04",
      "year": 2020,
      "abstract": "提出掩码语言模型预训练…"
    }
  },
  "meta": {}
}
```

---

## 2. Answer（被测系统输出）

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 对应题目 |
| `system` | str | 系统标识（adapter 自动填充，如 `studio`、`mock@water`） |
| `content` | str | 正文回答 |
| `citations` | list | 见 Citation |
| `tool_calls` | list | `[{"name": str, "args": {...}}]`，用于 T7/T8 |
| `meta` | object | `wall`（耗时）、`tokens`、`error`；**T5 必须提供 `verdict`** |

### Citation

| 字段 | 类型 | 说明 |
|------|------|------|
| `marker` | str | 正文中的引用标记，如 `[s1]` |
| `title` | str | 文献标题（用于 T3 匹配与 T1/T2 可解析率） |
| `doi` | str | DOI（可空） |
| `year` | int\|null | 年份 |
| `url` | str | 链接 |
| `source` | str | `openalex` / `crossref` / `arxiv` / `studio_search` / `mock` |

### T5 特殊约定

`meta.verdict` 必须为 `supported` / `unrelated` / `nonexistent` 之一。
若缺失，评测器会尝试从 `content` 前缀解析；仍失败则记为 `none`（按错误计）。

---

## 3. Answer Key（held-out 答案锚点）

文件：`data/v0.1/keys_heldout/T<n>.json`，形如 `{"T5-021": {...}}`。
**默认不公开**（已 gitignore），用于抗污染；外部系统通过提交 runner 由维护者跑分上榜。

| 族 | key 字段 |
|----|---------|
| T1 | `key_points`: list[str]（支持 `/` 分隔的别名）；`redlines`: list[str] |
| T2 | `key_points`；`experiment_elements`: list[str]；`redlines` |
| T3 | `gold_docs`: list[`{title, doi, year, cited_by_count}`] |
| T4 | `gold_answer`: str；`gold_spans`: list[str] |
| T5 | `verdict`: str；`claim`: str；`ref_title`: str |
| T6 | `reference_answer`: str；`writing_type`: str |
| T7 | `expected_tools`: list[str]；`key_points` |
| T8 | `expected_tools`: list[str]；`required_sections`: list[str] |

---

## 4. EvalResult（评测结果）

文件：`results/results_<system>.jsonl` 与 `results/results.jsonl`。

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` / `family` / `difficulty` / `system` | str | 标识 |
| `objective` | object | 各任务族的客观指标 |
| `objective_score` | float | 0–100 |
| `rubric` | list | `[{dim, score, reason, quote}]` |
| `rubric_score` | float | 0–100（1–5 加权平均映射） |
| `task_score` | float | `α·objective + (1-α)·rubric` |
| `errors` | list[str] | 失败归因标签 |
| `meta` | object | `wall`、`error`、`perturbation` |

### 失败归因标签（9 类）

`FACTUAL_HALLUCINATION` · `UNSUPPORTED_CITATION` · `MISSED_KEY_POINT` · `TERM_MISUSE` ·
`LOGIC_GAP` · `RETRIEVAL_MISS` · `TOOL_MISUSE` · `COMPLIANCE_RISK` · `VERBOSITY`

### 权重与 α 配置（schema.py）

| 族 | α（客观权重） | 族权重 w |
|----|--------------|---------|
| T1 | 0.45 | 0.18 |
| T2 | 0.35 | 0.12 |
| T3 | 0.85 | 0.12 |
| T4 | 0.70 | 0.16 |
| T5 | 0.85 | 0.14 |
| T6 | 0.45 | 0.10 |
| T7 | 0.60 | 0.10 |
| T8 | 0.70 | 0.08 |

---

## 5. 原子能力（C1–C8）

| 代码 | 能力 | 依赖该能力的任务族 |
|------|------|------------------|
| C1 | 检索召回 | T1 T3 T7 |
| C2 | 证据压缩 | T1 T2 |
| C3 | 长文理解 | T4 T6 |
| C4 | 引用溯源 | T4 T5 |
| C5 | 结构化生成 | T1 T2 T6 |
| C6 | 工具调用 | T3 T7 T8 |
| C7 | 多轮对话 | T7 T8 |
| C8 | 安全合规 | T1 T2 T4 T5 T8 |
