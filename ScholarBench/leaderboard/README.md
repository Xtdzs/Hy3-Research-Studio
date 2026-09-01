# Leaderboard

收录各系统在 ScholarBench 上的评测结果。**按数据集版本分列，不同版本不混排。**

---

## v0.1 · lite（64 条）

| 排名 | 系统 | 模型 | BenchScore | easy | medium | hard | 提交日期 |
|------|------|------|-----------|------|--------|------|---------|
| — | *待补充* | | | | | | |

> 结果文件存放于 `leaderboard/results/*.json`，字段格式见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

---

## 提交方式

见 [CONTRIBUTING.md §3](../CONTRIBUTING.md)。两种：

- **方式 A**：系统可公开访问 → 直接提交 `leaderboard/results/<name>.json`
- **方式 B**：系统闭源或需密钥 → 提交 adapter 代码 PR，由维护者代跑

---

## 比较注意事项

1. **必须同 split 比较**：lite 与 full 的分数不可直接比较
2. **必须同 judge 设置比较**：使用 `--no-judge` 的结果总分构成不同，不可与含 Rubric 的结果并列
3. **人类基线是绝对参照**：`human` adapter 的分数建议一并收录，否则读者无法判断"60 分算好还是差"
4. **同源偏差披露**：若 judge 与被测系统同族（如都用 Hy3），请标注，分数可能存在自评偏高
