# 数据来源与许可

ScholarBench 的数据全部来自**公开、开放获取**的来源，且构建脚本可复现。

---

## 代码

本仓库代码采用 **MIT License**。

## 数据集

数据集（`data/v0.1/`）中的**题目、关键点、合规红线**由本项目作者撰写，采用
**CC BY 4.0** 许可（署名即可自由使用）。

---

## 第三方数据来源

| 来源 | 用途 | 接口 | 许可 / 条款 |
|------|------|------|------------|
| [OpenAlex](https://openalex.org) | T3 gold 文献池（标题 / DOI / 年份 / 被引次数） | `https://api.openalex.org/works` | CC0 1.0（元数据） |
| [Crossref](https://www.crossref.org) | 备用文献元数据（经 Studio 检索层） | `https://api.crossref.org` | 元数据遵循 CC0 |
| [arXiv](https://arxiv.org) | T4 论文全文（PDF） | 各论文页 | 各论文自身的 arXiv 许可 |
| [PMC Open Access](https://www.ncbi.nlm.nih.gov/pmc/) | T4 可选全文来源 | OA Subset | 各论文的 OA 许可 |

**注意**：
- OpenAlex 与 Crossref 提供的是**文献元数据**（标题、作者、DOI、摘要），不含全文，均为 CC0。
- T4 需要的**论文全文 PDF 不随仓库分发**，请自行从 arXiv / PMC OA 下载并放入 `data/v0.1/papers/`（该目录已在 `.gitignore` 中排除 `*.pdf`）。
- 若你在生产环境中使用 gold 文献池，请遵守 OpenAlex 的[使用条款](https://openalex.org/access)与礼貌抓取（polite pool）规范。

---

## 引用标注

T5 的引用核对样本使用公开可查的经典文献元数据（标题 / DOI / 摘要片段）作为**构造材料**，
其中"nonexistent"类样本的标题与 DOI 均为**程序化生成的虚构内容**，不指向任何真实出版物。

---

## 引用本数据集

```bibtex
@misc{scholarbench2026,
  title  = {ScholarBench: An End-to-End Benchmark for Academic Research Workflows},
  author = {Tencent Rhino Bird Open Source Talent Program},
  year   = {2026},
  note   = {v0.1},
}
```
