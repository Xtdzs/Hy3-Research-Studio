"""Multi-source evidence search.

默认使用**免 Key、稳定**的学术检索源，开箱即跑、能真正检索到文献：

- OpenAlex   (https://api.openalex.org)   免费、限流宽松、元数据丰富
- Crossref   (https://api.crossref.org)   免费、极稳定、含 DOI/摘要
- arXiv      (Atom API)                   免费、覆盖预印本

可选增强（仅当提供 ``S2_API_KEY`` 时启用，提升召回与稳定性）：

- Semantic Scholar (Graph API)

所有网络请求均为 best-effort：失败优雅降级，不会中断研究流程。
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import httpx

from .config import settings
from .models import SourceDocument, SourceType

_OPENALEX = "https://api.openalex.org/works"
_CROSSREF = "https://api.crossref.org/works"
_ARXIV = "https://export.arxiv.org/api/query"
_S2 = "https://api.semanticscholar.org/graph/v1/paper/search"
_ATOM = "{http://www.w3.org/2005/Atom}"

# OpenAlex / Crossref 要求提供 UA；这里用占位邮箱，可替换为项目联系邮箱。
_UA = "Hy3ResearchStudio/1.0 (mailto:hy3-studio@example.com)"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _stable_id(title: str) -> str:
    h = hashlib.md5(title.lower().encode("utf-8")).hexdigest()[:10]
    return "L" + h


def _reconstruct_abstract(inv_index: Optional[dict]) -> str:
    """OpenAlex 用倒排索引存储摘要，需要还原成可读文本。"""
    if not inv_index:
        return ""
    try:
        length = max(max(pos) for pos in inv_index.values()) + 1
    except Exception:  # noqa: BLE001
        return ""
    words = [""] * length
    for word, positions in inv_index.items():
        for p in positions:
            words[p] = word
    return _clean(" ".join(words))


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------
def search_openalex(query: str, limit: int, year: Optional[int] = None, page: int = 1,
                    oa: bool = False, doc_type: Optional[str] = None) -> list[SourceDocument]:
    params = {
        "search": query,
        "per_page": min(limit, 50),
        "page": max(1, page),
        "select": "id,display_name,authorships,publication_year,primary_location,abstract_inverted_index,doi,cited_by_count",
        "sort": "relevance_score:desc",
    }
    flt: list[str] = []
    if year:
        cur = datetime.now().year
        flt.append(f"publication_year:{year}-{cur}")
    if oa:
        flt.append("is_oa:true")
    if doc_type == "article":
        flt.append("type:article")
    elif doc_type == "preprint":
        flt.append("type:preprint")
    elif doc_type == "book":
        flt.append("type:book")
    if flt:
        params["filter"] = ",".join(flt)
    out: list[SourceDocument] = []
    try:
        r = httpx.get(_OPENALEX, params=params, timeout=settings.http_timeout,
                      headers={"User-Agent": _UA})
        r.raise_for_status()
        for item in r.json().get("results", []) or []:
            title = _clean(item.get("display_name") or "")
            if not title:
                continue
            authors = [
                _clean(a.get("author", {}).get("display_name", ""))
                for a in (item.get("authorships") or [])[:6]
            ]
            venue = ""
            loc = item.get("primary_location") or {}
            src = loc.get("source") or {}
            venue = _clean(src.get("display_name") or "")
            url = item.get("doi") or item.get("id")
            abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
            out.append(
                SourceDocument(
                    source_id=_stable_id(title + (venue or "")),
                    title=title,
                    source_type=SourceType.paper,
                    url=url,
                    authors=[a for a in authors if a],
                    year=str(item.get("publication_year") or ""),
                    venue=venue or "OpenAlex",
                    abstract=abstract,
                    snippet=abstract[:600],
                )
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[search] OpenAlex failed for '{query}': {exc}")
    return out


# ---------------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------------
def search_crossref(query: str, limit: int, year: Optional[int] = None, page: int = 1,
                     oa: bool = False, doc_type: Optional[str] = None) -> list[SourceDocument]:
    rows = min(limit, 50)
    params = {
        "query": query,
        "rows": rows,
        "offset": max(0, page - 1) * rows,
        "select": "title,author,issued,container-title,URL,abstract,DOI,type",
        "sort": "relevance",
    }
    flt: list[str] = []
    if year:
        cur = datetime.now().year
        flt.append(f"from-pub-date:{year}-01-01")
        flt.append(f"until-pub-date:{cur}-12-31")
    if oa:
        flt.append("has-full-text:true")
    if doc_type == "article":
        flt.append("type:journal-article")
    elif doc_type == "preprint":
        flt.append("type:posted-content")
    elif doc_type == "book":
        flt.append("type:book")
    if flt:
        params["filter"] = ",".join(flt)
    out: list[SourceDocument] = []
    try:
        r = httpx.get(_CROSSREF, params=params, timeout=settings.http_timeout,
                      headers={"User-Agent": _UA})
        r.raise_for_status()
        for item in r.json().get("message", {}).get("items", []) or []:
            title = _clean((item.get("title") or [""])[0])
            if not title:
                continue
            authors = [
                _clean(f"{a.get('given', '')} {a.get('family', '')}")
                for a in (item.get("author") or [])[:6]
            ]
            year_val = ""
            issued = item.get("issued") or {}
            parts = issued.get("date-parts") or [[]]
            if parts and parts[0]:
                year_val = str(parts[0][0])
            venue = _clean((item.get("container-title") or [""])[0])
            abstract = _clean(item.get("abstract") or "")
            # Crossref 摘要常为 JATS XML，去掉标签
            abstract = re.sub(r"<[^>]+>", " ", abstract)
            out.append(
                SourceDocument(
                    source_id=_stable_id(title + (venue or "")),
                    title=title,
                    source_type=SourceType.paper,
                    url=item.get("URL") or item.get("DOI"),
                    authors=[a for a in authors if a],
                    year=year_val,
                    venue=venue or "Crossref",
                    abstract=abstract,
                    snippet=abstract[:600],
                )
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[search] Crossref failed for '{query}': {exc}")
    return out


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------
def search_arxiv(query: str, limit: int, page: int = 1,
                 oa: bool = False, doc_type: Optional[str] = None) -> list[SourceDocument]:
    # arXiv 仅含预印本：筛选"期刊论文/图书"时该源无结果；开放获取对其恒为真。
    if doc_type in ("article", "book"):
        return []
    # 用括号包裹多词查询，提升召回相关性
    q = query if " " not in query else f"all:\"{query}\""
    n = min(limit, 50)
    params = {
        "search_query": q,
        "start": max(0, page - 1) * n,
        "max_results": n,
        "sortBy": "relevance",
    }
    out: list[SourceDocument] = []
    try:
        r = httpx.get(_ARXIV, params=params, timeout=settings.http_timeout)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for entry in root.findall(f"{_ATOM}entry"):
            arxiv_id = _clean(entry.findtext(f"{_ATOM}id", ""))
            short_id = arxiv_id.rstrip("/").split("/")[-1]
            title = _clean(entry.findtext(f"{_ATOM}title", ""))
            if not title:
                continue
            summary = _clean(entry.findtext(f"{_ATOM}summary", ""))
            published = _clean(entry.findtext(f"{_ATOM}published", ""))
            year = published[:4] if published else None
            authors = [
                _clean(a.findtext(f"{_ATOM}name", ""))
                for a in entry.findall(f"{_ATOM}author")
            ]
            out.append(
                SourceDocument(
                    source_id=_stable_id(title),
                    title=title,
                    source_type=SourceType.paper,
                    url=arxiv_id,
                    authors=authors[:6],
                    year=year,
                    venue=f"arXiv:{short_id}",
                    abstract=summary,
                    snippet=summary[:600],
                )
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[search] arXiv failed for '{query}': {exc}")
    return out


# ---------------------------------------------------------------------------
# Semantic Scholar (optional, requires S2_API_KEY)
# ---------------------------------------------------------------------------
def search_semantic_scholar(query: str, limit: int, page: int = 1,
                             oa: bool = False, doc_type: Optional[str] = None) -> list[SourceDocument]:
    if not settings.s2_api_key:
        return []
    n = min(limit, 50)
    params = {
        "query": query,
        "limit": n,
        "offset": max(0, page - 1) * n,
        "fields": "title,abstract,year,authors,venue,url,externalIds",
    }
    headers = {"x-api-key": settings.s2_api_key}
    out: list[SourceDocument] = []
    try:
        r = httpx.get(_S2, params=params, headers=headers, timeout=settings.http_timeout)
        if r.status_code != 200:
            return out
        for item in r.json().get("data", []) or []:
            abstract = _clean(item.get("abstract") or "")
            if not abstract:
                continue
            authors = [a.get("name", "") for a in (item.get("authors") or [])][:6]
            out.append(
                SourceDocument(
                    source_id=_stable_id(_clean(item.get("title") or "")),
                    title=_clean(item.get("title") or "Untitled"),
                    source_type=SourceType.paper,
                    url=item.get("url"),
                    authors=authors,
                    year=str(item.get("year")) if item.get("year") else None,
                    venue=_clean(item.get("venue") or "Semantic Scholar"),
                    abstract=abstract,
                    snippet=abstract[:600],
                )
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[search] Semantic Scholar failed for '{query}': {exc}")
    return out


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------
def _dedupe(docs: list[SourceDocument]) -> list[SourceDocument]:
    seen: dict[str, SourceDocument] = {}
    for d in docs:
        key = re.sub(r"[^a-z0-9]", "", d.title.lower())[:60]
        if key and key not in seen:
            seen[key] = d
    return list(seen.values())


def _search_one(src: str, query: str, per: int, year: Optional[int], page: int,
                oa: bool = False, doc_type: Optional[str] = None) -> list[SourceDocument]:
    if src == "openalex":
        return search_openalex(query, per, year, page, oa, doc_type)
    if src == "crossref":
        return search_crossref(query, per, year, page, oa, doc_type)
    if src == "arxiv":
        return search_arxiv(query, per, page, oa, doc_type)
    if src == "semantic_scholar":
        return search_semantic_scholar(query, per, page, oa, doc_type)
    return []


def _to_item(d: SourceDocument) -> dict:
    item = d.model_dump()
    item["retrieved_from"] = _guess_source(d.url, d.venue)
    return item


def search_literature(
    query: str,
    sources: Optional[list[str]] = None,
    limit: int = 20,
    year: Optional[int] = None,
    page: int = 1,
    oa: bool = False,
    doc_type: Optional[str] = None,
) -> list[dict]:
    """面向「文献检索」页面的跨源搜索，返回 SourceDocument 的 dict 列表。

    每个来源都抓取 ``limit`` 条（而非平分），聚合去重后返回，避免"只有一页/结果太少"。
    ``page`` 支持翻页/加载更多；``oa``/``doc_type`` 为跨源通用的"最大公约数"筛选条件。
    """
    sources = sources or settings.default_sources
    per = min(max(limit, 5), 50)
    results: list[SourceDocument] = []
    for src in sources:
        results += _search_one(src, query, per, year, page, oa, doc_type)
    results = _dedupe(results)
    return [_to_item(d) for d in results]


def search_literature_iter(
    query: str,
    sources: Optional[list[str]] = None,
    limit: int = 20,
    year: Optional[int] = None,
    page: int = 1,
    oa: bool = False,
    doc_type: Optional[str] = None,
):
    """流式版本：每检索完一个来源就 yield 一批结果，供 SSE 边检索边展示。

    yield ("source_batch", {source, items, count}) / ("done", {total}).
    """
    sources = sources or settings.default_sources
    per = min(max(limit, 5), 50)
    seen: dict[str, SourceDocument] = {}
    total = 0
    for src in sources:
        docs = _search_one(src, query, per, year, page, oa, doc_type)
        batch: list[dict] = []
        for d in docs:
            key = re.sub(r"[^a-z0-9]", "", d.title.lower())[:60]
            if not key or key in seen:
                continue
            seen[key] = d
            batch.append(_to_item(d))
        total += len(batch)
        yield "source_batch", {"source": src, "items": batch, "count": len(batch)}
    yield "done", {"total": total}


def _guess_source(url: Optional[str], venue: Optional[str]) -> str:
    if url and "arxiv.org" in (url or ""):
        return "arXiv"
    if venue and "arxiv" in (venue or "").lower():
        return "arXiv"
    if venue and venue in ("OpenAlex", "Crossref"):
        return venue
    return venue or "学术数据库"


def gather_sources(
    queries: list[str],
    use_paper: bool,
    per_query: Optional[int] = None,
) -> list[SourceDocument]:
    """供研究流水线使用：围绕子问题检索并去重。"""
    per_query = per_query or settings.max_sources_per_query
    sources = settings.default_sources if use_paper else []
    if use_paper and not sources:
        sources = ["openalex", "crossref", "arxiv"]
    out: list[SourceDocument] = []
    for q in queries:
        for src in sources:
            if src == "openalex":
                out += search_openalex(q, per_query)
            elif src == "crossref":
                out += search_crossref(q, per_query)
            elif src == "arxiv":
                out += search_arxiv(q, per_query)
            elif src == "semantic_scholar":
                out += search_semantic_scholar(q, per_query)
    return _dedupe(out)
