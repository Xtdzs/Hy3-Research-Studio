# 参与 ScholarBench

三种贡献方式：**加任务**、**加 adapter**、**提交结果**。

---

## 1. 新增任务题

1. 在 `scholarbench/seedbank.py` 中给对应族的 `T<n>_SEEDS` 追加条目（含 `id` / `d`(难度) / `q`(题目) / `kp`(关键点) 等字段）
2. 运行 `python -m scholarbench build_dataset --offline` 重新生成 `data/v0.1/` 与 splits
3. 提交 PR 时**只提交 `seedbank.py` 与 `data/v0.1/T*.jsonl`**，不要提交 `keys_heldout/`

### 出题规范

- **难度梯度**：每族保持 easy : medium : hard ≈ 2 : 3 : 3
- **hard 样本**必须选取模型易失败类型之一：冷门/新方向、需要否定性结论、多跳对比、证据冲突、引用易被伪造
- **key_points** 用「中文 或 英文原文」给出，多个别名用 `/` 分隔（如 `chunk summarization / 摘要式压缩`）
- **redlines** 只写确实会导致合规风险的词，不要滥用（误报会污染 D6）

---

## 2. 新增 Adapter

在 `scholarbench/adapters/` 下新建文件，实现 `generate(task) -> Answer`：

```python
from scholarbench.adapters.base import SUT
from scholarbench.schema import Answer, Task

class MyAdapter(SUT):
    name = "my_adapter"

    def __init__(self, arg1="", **kwargs):
        super().__init__(**kwargs)
        self.arg1 = arg1

    def generate(self, task: Task) -> Answer:
        try:
            text = run_my_system(task.prompt, task.context)
            return Answer(task_id=task.task_id, system=self.name,
                          content=text, meta={})
        except Exception as exc:
            # 异常不要抛出，写入 meta['error']，评测不会中断
            return Answer(task_id=task.task_id, system=self.name,
                          content="", meta={"error": str(exc)})
```

然后在 `adapters/__init__.py` 的 `get_adapter()` 中注册：

```python
if kind == "my_adapter":
    from .my_adapter import MyAdapter
    return MyAdapter(arg1=arg)
```

**约定**：
- 异常必须内部消化（写入 `meta["error"]`），不要把整个评测跑崩
- T5 必须在 `meta["verdict"]` 返回三分类之一
- T7/T8 要如实回填 `tool_calls`，否则工具调用指标会失真
- 不要缓存跨题目的状态（每题独立）

---

## 3. 提交评测结果上 Leaderboard

### 方式 A：系统可公开访问（推荐）

在 `leaderboard/results/` 下新增 `<system-name>.json`：

```json
{
  "system": "my_system",
  "version": "scholarbench-v0.1",
  "split": "lite",
  "model": "my-model-7b",
  "adapter": "http:https://my.host/api/bench",
  "date": "2026-09-01",
  "scores": {
    "bench_score": 62.4,
    "family": {"T1": 71.0, "T2": 58.2, "T3": 49.5, "T4": 66.1,
               "T5": 80.3, "T6": 55.4, "T7": 60.2, "T8": 52.8},
    "difficulty": {"easy": 74.1, "medium": 63.0, "hard": 48.7}
  },
  "reproduce": "python -m scholarbench run --split lite --systems http:https://my.host/api/bench",
  "notes": "无检索增强，仅裸模型"
}
```

### 方式 B：系统不可公开（闭源 / 需密钥）

提交 adapter 代码 PR，由维护者代跑后写入结果文件。
这样可以同时验证结果真实性，且**答案锚点不会外泄**。

### 结果要求

- 必须注明 `split`（lite / full）与 `model`
- `reproduce` 字段必须是可直接复制执行的命令
- 若使用了 `--no-judge`，需在 `notes` 中说明（此时总分不可与含 Rubric 的结果直接比较）

---

## 4. 修改指标体系

改动 `metrics/rubric.py`（维度与锚点）、`metrics/objective.py`（规则指标）或 `schema.py`（权重 α）都会影响分数可比性。请：

1. 在 PR 中说明改动理由与影响范围
2. **提升数据集版本号**（`v0.1` → `v0.2`）并重新生成数据
3. 在 Leaderboard 中按版本分列，不混排不同版本的结果

---

## 5. 代码风格

- Python 3.10+，类型注解可选但推荐
- 公开函数写 docstring，说明「判什么 / 为什么」
- 新增客观指标必须是**确定性**的（不调用 LLM），否则请放进 Rubric
- 纯标准库能实现的，不引入依赖（一致性检验就是纯标准库实现的）
