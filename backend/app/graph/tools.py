"""
app.graph.tools
~~~~~~~~~~~~~~~~
Async research tools for medical literature search.

Each tool:
• is fully async
• supports retries via tenacity
• supports configurable timeout
• returns typed Pydantic models
• normalises evidence scores

Agents invoke tools via JSON tool-call format:
    {"tool": "pubmed_search", "query": "acute coronary syndrome troponin"}

TOOL ROSTER
───────────
• tavily_search           — Tavily web search (medical-scoped)
• pubmed_search           — PubMed / Europe PMC
• semantic_scholar_search — Semantic Scholar academic papers
• google_custom_search    — Google CSE
• wikipedia_lookup        — Wikipedia disease reference
• literature_search       — Aggregated PubMed + Semantic Scholar
• clinical_guidelines     — Site-restricted guideline search
• clinical_database       — Clinical database stub (returns null)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.exceptions import ToolError, ToolTimeoutError
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Result models ────────────────────────────────────────────────────


class EvidenceItem(BaseModel):
    """A single piece of research evidence."""

    title: str = ""
    snippet: str = ""
    url: str = ""
    source: str = ""
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    year: int | None = None
    authors: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    """Standardised output from any research tool."""

    tool_name: str
    query: str
    results: list[EvidenceItem] = Field(default_factory=list)
    total_found: int = 0
    error: str | None = None


# ── Retry decorator ──────────────────────────────────────────────────

_retry_tool = retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5, min=1, max=10),
    reraise=True,
)


# =====================================================================
# 1) TAVILY MEDICAL LITERATURE SEARCH
# =====================================================================


@_retry_tool
async def tavily_search(query: str, *, max_results: int = 5) -> ToolResult:
    """Search medical literature via Tavily API."""
    settings = get_settings()
    if not settings.tavily_api_key:
        return ToolResult(tool_name="tavily", query=query, error="TAVILY_API_KEY not configured")

    async with httpx.AsyncClient(timeout=settings.tool_timeout) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": f"medical {query}",
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": True,
            },
        )

    if resp.status_code != 200:
        return ToolResult(
            tool_name="tavily", query=query, error=f"HTTP {resp.status_code}"
        )

    data = resp.json()
    results = []
    for r in data.get("results", []):
        results.append(
            EvidenceItem(
                title=r.get("title", ""),
                snippet=r.get("content", "")[:500],
                url=r.get("url", ""),
                source="tavily",
                relevance_score=min(r.get("score", 0.5), 1.0),
            )
        )

    return ToolResult(
        tool_name="tavily",
        query=query,
        results=results,
        total_found=len(results),
    )


# =====================================================================
# 2) PUBMED / EUROPE PMC
# =====================================================================


@_retry_tool
async def pubmed_search(query: str, *, max_results: int = 5) -> ToolResult:
    """Search PubMed via the Europe PMC REST API (no API key required)."""
    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results,
        "sort": "RELEVANCE",
    }
    async with httpx.AsyncClient(timeout=get_settings().tool_timeout) as client:
        resp = await client.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params=params,
        )

    if resp.status_code != 200:
        return ToolResult(
            tool_name="pubmed", query=query, error=f"HTTP {resp.status_code}"
        )

    data = resp.json()
    result_list = data.get("resultList", {}).get("result", [])
    results = []
    for r in result_list:
        pmid = r.get("pmid", "")
        results.append(
            EvidenceItem(
                title=r.get("title", ""),
                snippet=r.get("abstractText", "")[:500],
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}" if pmid else "",
                source="pubmed",
                relevance_score=0.7,  # PMC doesn't return relevance scores
                year=_safe_int(r.get("pubYear")),
                authors=[
                    a.get("fullName", "")
                    for a in r.get("authorList", {}).get("author", [])[:5]
                ],
            )
        )

    return ToolResult(
        tool_name="pubmed",
        query=query,
        results=results,
        total_found=int(data.get("hitCount", len(results))),
    )


# =====================================================================
# 3) SEMANTIC SCHOLAR
# =====================================================================


@_retry_tool
async def semantic_scholar_search(
    query: str, *, max_results: int = 5
) -> ToolResult:
    """Search Semantic Scholar for academic papers."""
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,url,year,authors,citationCount",
    }
    async with httpx.AsyncClient(timeout=get_settings().tool_timeout) as client:
        resp = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
        )

    if resp.status_code != 200:
        return ToolResult(
            tool_name="semantic_scholar",
            query=query,
            error=f"HTTP {resp.status_code}",
        )

    data = resp.json()
    results = []
    for paper in data.get("data", []):
        cites = paper.get("citationCount", 0) or 0
        # Normalise citation count to a 0–1 relevance proxy
        score = min(cites / 500, 1.0) if cites else 0.3
        results.append(
            EvidenceItem(
                title=paper.get("title", ""),
                snippet=(paper.get("abstract") or "")[:500],
                url=paper.get("url", ""),
                source="semantic_scholar",
                relevance_score=round(score, 2),
                year=paper.get("year"),
                authors=[
                    a.get("name", "")
                    for a in (paper.get("authors") or [])[:5]
                ],
            )
        )

    return ToolResult(
        tool_name="semantic_scholar",
        query=query,
        results=results,
        total_found=data.get("total", len(results)),
    )


# =====================================================================
# 4) GOOGLE CUSTOM SEARCH
# =====================================================================


@_retry_tool
async def google_custom_search(
    query: str, *, max_results: int = 5
) -> ToolResult:
    """Search via Google Custom Search Engine API."""
    settings = get_settings()
    if not settings.google_cse_api_key or not settings.google_cse_cx:
        return ToolResult(
            tool_name="google_cse",
            query=query,
            error="Google CSE credentials not configured",
        )

    params = {
        "key": settings.google_cse_api_key,
        "cx": settings.google_cse_cx,
        "q": f"medical {query}",
        "num": min(max_results, 10),
    }
    async with httpx.AsyncClient(timeout=settings.tool_timeout) as client:
        resp = await client.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
        )

    if resp.status_code != 200:
        return ToolResult(
            tool_name="google_cse",
            query=query,
            error=f"HTTP {resp.status_code}",
        )

    data = resp.json()
    results = []
    for item in data.get("items", []):
        results.append(
            EvidenceItem(
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                url=item.get("link", ""),
                source="google_cse",
                relevance_score=0.6,
            )
        )

    return ToolResult(
        tool_name="google_cse",
        query=query,
        results=results,
        total_found=int(
            data.get("searchInformation", {}).get("totalResults", len(results))
        ),
    )


# =====================================================================
# 5) WIKIPEDIA DISEASE LOOKUP
# =====================================================================


@_retry_tool
async def wikipedia_lookup(query: str) -> ToolResult:
    """Look up a disease or medical condition on Wikipedia."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 3,
        "utf8": 1,
    }
    async with httpx.AsyncClient(timeout=get_settings().tool_timeout) as client:
        resp = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params=params,
        )

    if resp.status_code != 200:
        return ToolResult(
            tool_name="wikipedia",
            query=query,
            error=f"HTTP {resp.status_code}",
        )

    data = resp.json()
    results = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "").replace('<span class="searchmatch">', "").replace("</span>", "")
        results.append(
            EvidenceItem(
                title=title,
                snippet=snippet[:500],
                url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                source="wikipedia",
                relevance_score=0.5,
            )
        )

    return ToolResult(
        tool_name="wikipedia",
        query=query,
        results=results,
        total_found=len(results),
    )


# =====================================================================
# 6) LITERATURE SEARCH (aggregated PubMed + Semantic Scholar)
# =====================================================================


async def literature_search(query: str, *, max_results: int = 5) -> ToolResult:
    """
    Aggregated literature search across PubMed and Semantic Scholar.

    Merges results from both sources, deduplicates by title similarity,
    and returns the top results ranked by relevance.
    """
    logger.info("literature_search_start", query=query[:100])

    # Run both searches concurrently
    pubmed_task = pubmed_search(query, max_results=max_results)
    scholar_task = semantic_scholar_search(query, max_results=max_results)

    results = await asyncio.gather(pubmed_task, scholar_task, return_exceptions=True)

    merged: list[EvidenceItem] = []
    errors: list[str] = []

    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
            continue
        merged.extend(r.results)

    # Deduplicate by normalised title
    seen_titles: set[str] = set()
    deduped: list[EvidenceItem] = []
    for item in merged:
        norm_title = item.title.strip().lower()[:80]
        if norm_title and norm_title not in seen_titles:
            seen_titles.add(norm_title)
            deduped.append(item)

    # Sort by relevance score descending
    deduped.sort(key=lambda x: x.relevance_score, reverse=True)
    deduped = deduped[:max_results * 2]  # return up to 2x max

    return ToolResult(
        tool_name="literature_search",
        query=query,
        results=deduped,
        total_found=len(deduped),
        error="; ".join(errors) if errors else None,
    )


# =====================================================================
# 7) CLINICAL GUIDELINES SEARCH
# =====================================================================


async def clinical_guidelines(query: str, *, max_results: int = 5) -> ToolResult:
    """
    Search clinical practice guidelines from trusted sources.

    Uses Google CSE with site-restricted queries targeting:
    - WHO guidelines
    - NICE (UK) guidelines
    - UpToDate references
    - CDC clinical guidelines
    - AHA/ACC guidelines

    Falls back to a regular Google CSE search with guideline keywords
    if no specific guideline results are found.
    """
    settings = get_settings()

    if not settings.google_cse_api_key or not settings.google_cse_cx:
        # Fallback: search PubMed for guideline-type papers
        logger.info("clinical_guidelines_fallback_pubmed", query=query[:100])
        return await pubmed_search(
            f"{query} clinical practice guideline recommendation",
            max_results=max_results,
        )

    # Site-restricted guideline query
    guideline_query = (
        f"{query} clinical guideline practice recommendation "
        f"(site:who.int OR site:nice.org.uk OR site:cdc.gov OR "
        f"site:heart.org OR site:acc.org)"
    )

    params = {
        "key": settings.google_cse_api_key,
        "cx": settings.google_cse_cx,
        "q": guideline_query,
        "num": min(max_results, 10),
    }

    try:
        async with httpx.AsyncClient(timeout=settings.tool_timeout) as client:
            resp = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
            )

        if resp.status_code != 200:
            # Fallback to PubMed guideline search
            logger.warning(
                "clinical_guidelines_cse_failed",
                status=resp.status_code,
            )
            return await pubmed_search(
                f"{query} clinical practice guideline",
                max_results=max_results,
            )

        data = resp.json()
        results = []
        for item in data.get("items", []):
            url = item.get("link", "")
            # Boost relevance for known guideline domains
            score = 0.7
            if any(domain in url for domain in ["who.int", "nice.org.uk", "cdc.gov"]):
                score = 0.9
            elif any(domain in url for domain in ["heart.org", "acc.org"]):
                score = 0.85

            results.append(
                EvidenceItem(
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    url=url,
                    source="clinical_guidelines",
                    relevance_score=score,
                )
            )

        if not results:
            # No guideline results found, fallback
            return await pubmed_search(
                f"{query} clinical practice guideline",
                max_results=max_results,
            )

        return ToolResult(
            tool_name="clinical_guidelines",
            query=query,
            results=results,
            total_found=len(results),
        )

    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        logger.warning("clinical_guidelines_error", error=str(exc))
        return await pubmed_search(
            f"{query} clinical practice guideline",
            max_results=max_results,
        )


# =====================================================================
# 8) CLINICAL DATABASE (stub — not yet available)
# =====================================================================


async def clinical_database(query: str) -> ToolResult:
    """
    Clinical database lookup — stub implementation.

    Returns an empty result indicating the database is not yet available.
    All callers handle null/empty results gracefully.
    """
    logger.info("clinical_database_stub", query=query[:100])
    return ToolResult(
        tool_name="clinical_database",
        query=query,
        results=[],
        total_found=0,
        error="Clinical database not yet available. This is a planned feature.",
    )


# =====================================================================
# TOOL DISPATCHER
# =====================================================================

# Registry maps tool names → callables
TOOL_REGISTRY: dict[str, Any] = {
    "tavily_search": tavily_search,
    "pubmed_search": pubmed_search,
    "semantic_scholar_search": semantic_scholar_search,
    "google_custom_search": google_custom_search,
    "wikipedia_lookup": wikipedia_lookup,
    "literature_search": literature_search,
    "clinical_guidelines": clinical_guidelines,
    "clinical_database": clinical_database,
}


async def execute_tool_call(
    tool_name: str,
    query: str,
    *,
    timeout: float | None = None,
) -> ToolResult:
    """
    Dispatch a tool call by name.

    Raises ``ToolError`` if the tool is unknown.
    Raises ``ToolTimeoutError`` if the call exceeds the deadline.
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        raise ToolError(f"Unknown tool: {tool_name}", details={"tool": tool_name})

    effective_timeout = timeout or get_settings().tool_timeout

    try:
        result = await asyncio.wait_for(fn(query), timeout=effective_timeout)
        logger.info("tool_call_complete", tool=tool_name, query=query[:100])
        return result
    except asyncio.TimeoutError:
        raise ToolTimeoutError(
            f"Tool '{tool_name}' timed out after {effective_timeout}s",
            details={"tool": tool_name, "query": query},
        )


async def execute_tool_calls_batch(
    calls: list[dict[str, str]],
) -> list[ToolResult]:
    """Execute multiple tool calls concurrently and return all results."""
    tasks = [
        execute_tool_call(c.get("tool", ""), c.get("query", ""))
        for c in calls
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.warning(
                "tool_call_failed",
                tool=calls[i].get("tool"),
                error=str(r),
            )
            final.append(
                ToolResult(
                    tool_name=calls[i].get("tool", "unknown"),
                    query=calls[i].get("query", ""),
                    error=str(r),
                )
            )
        else:
            final.append(r)
    return final


# ── Helpers ──────────────────────────────────────────────────────────


def _safe_int(val: Any) -> int | None:
    """Convert to int safely, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
