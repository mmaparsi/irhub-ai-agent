"""Web search via SearXNG, with optional Tavily or Brave."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def search_web(query: str, limit: int = 5) -> list[dict]:
    limit = max(1, min(int(limit or 5), 10))
    from app.tools.providers import StubSearchProvider, get_search_provider

    provider = get_search_provider()
    if not isinstance(provider, StubSearchProvider):
        return provider.search(query, limit=limit)
    errors: list[str] = []
    if settings.searxng_url.strip():
        try:
            return _searxng(query, limit)
        except Exception as exc:
            logger.warning("searxng search failed: %s", exc)
            errors.append(f"SearXNG: {exc}")
    if settings.tavily_api_key.strip():
        try:
            return _tavily(query, limit)
        except Exception as exc:
            logger.warning("tavily search failed: %s", exc)
            errors.append(f"Tavily: {exc}")
    if settings.brave_api_key.strip():
        try:
            return _brave(query, limit)
        except Exception as exc:
            logger.warning("brave search failed: %s", exc)
            errors.append(f"Brave: {exc}")
    detail = "؛ ".join(errors) if errors else "هیچ ارائه‌دهندهٔ جست‌وجویی تنظیم نشده است."
    raise RuntimeError(detail)


def _client() -> httpx.Client:
    return httpx.Client(timeout=8, trust_env=True, follow_redirects=True)


def _searxng(query: str, limit: int) -> list[dict]:
    base = settings.searxng_url.strip().rstrip("/")
    with _client() as client:
        response = client.get(f"{base}/search", params={"q": query, "format": "json"})
        response.raise_for_status()
        payload = response.json()
    rows = []
    for item in (payload.get("results") or [])[:limit]:
        rows.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or "",
            }
        )
    return rows


def _tavily(query: str, limit: int) -> list[dict]:
    with _client() as client:
        response = client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key.strip(),
                "query": query,
                "max_results": limit,
            },
        )
        response.raise_for_status()
        payload = response.json()
    return [
        {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "snippet": item.get("content") or "",
        }
        for item in (payload.get("results") or [])[:limit]
    ]


def _brave(query: str, limit: int) -> list[dict]:
    with _client() as client:
        response = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": limit},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": settings.brave_api_key.strip(),
            },
        )
        response.raise_for_status()
        payload = response.json()
    web = ((payload.get("web") or {}).get("results")) or []
    return [
        {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "snippet": item.get("description") or "",
        }
        for item in web[:limit]
    ]
