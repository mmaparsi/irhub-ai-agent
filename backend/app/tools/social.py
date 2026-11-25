"""LinkedIn and Facebook discovery.

The default provider searches the public web with site: operators. A Playwright
session that reuses the owner's own cookies is optional and off by default.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol

from app.config import settings
from app.runtime.events import note_progress
from app.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

_CITIES = ("تهران", "اصفهان", "تبریز", "مشهد", "شیراز", "رشت", "کرج", "اهواز", "قم", "یزد")
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w.\-]+\.\w+")
_PHONE_RE = re.compile(r"(?:\+98|0)\d[\d\-\s]{8,}\d")
_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_playwright_hits: list[float] = []


class SocialProvider(Protocol):
    name: str

    def search(self, *, network: str, query: str, kind: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError


def build_query(network: str, query: str, kind: str) -> str:
    text = (query or "").strip()
    if network == "linkedin":
        site = "site:linkedin.com/in" if kind == "person" else "site:linkedin.com/company"
    else:
        site = "site:facebook.com"
    return f"{site} {text}".strip()


def extract_hit(network: str, hit: dict[str, Any]) -> dict[str, Any]:
    title = str(hit.get("title") or "")
    name = re.split(r"\s+[|\-–—]\s+", title)[0].strip() or title.strip()
    snippet = str(hit.get("snippet") or hit.get("content") or "")
    blob = f"{title}\n{snippet}"
    website = ""
    for url in _URL_RE.findall(blob):
        lowered = url.lower()
        if "linkedin.com" in lowered or "facebook.com" in lowered:
            continue
        website = url.rstrip(".,")
        break
    location = next((city for city in _CITIES if city in blob), "")
    return {
        "name": name,
        "website": website,
        "industry": "",
        "location": location,
        "emails": _EMAIL_RE.findall(blob),
        "phones": [re.sub(r"\s+", "", item) for item in _PHONE_RE.findall(blob)],
        "url": str(hit.get("url") or ""),
        "snippet": snippet,
        "source": network,
    }


class PublicWebProvider:
    name = "public_web"

    def search(self, *, network: str, query: str, kind: str, limit: int) -> list[dict[str, Any]]:
        from app.tools.search import search_web

        rows = search_web(build_query(network, query, kind), limit=limit)
        return [extract_hit(network, row) for row in rows]


class PlaywrightSessionProvider:
    """Uses the owner's browser cookies. Disabled unless the feature flag is on."""

    name = "playwright_session"

    def search(self, *, network: str, query: str, kind: str, limit: int) -> list[dict[str, Any]]:
        reserve_playwright_slot()
        cookies = _cookies()
        url = _search_url(network, query, kind)
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("مرورگر برای جلسهٔ شبکهٔ اجتماعی نصب نیست.") from exc
        snippets: list[dict[str, Any]] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                if cookies:
                    context.add_cookies(cookies)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                texts = page.locator("a").all_inner_texts()
                hrefs = page.locator("a").evaluate_all(
                    "nodes => nodes.map(node => node.href || '')"
                )
                for title, href in list(zip(texts, hrefs, strict=False))[:limit]:
                    if network == "linkedin" and "linkedin.com" not in href:
                        continue
                    if network == "facebook" and "facebook.com" not in href:
                        continue
                    snippets.append({"title": title.strip(), "url": href, "snippet": title.strip()})
                browser.close()
        except Exception as exc:
            raise RuntimeError("جست‌وجوی جلسهٔ مرورگر ناموفق بود.") from exc
        logger.info("playwright social search network=%s results=%s", network, len(snippets))
        return [extract_hit(network, row) for row in snippets[:limit]]


def reserve_playwright_slot() -> None:
    now = time.time()
    window = [item for item in _playwright_hits if now - item < 3600]
    _playwright_hits[:] = window
    if len(_playwright_hits) >= max(1, settings.social_playwright_hourly_limit):
        raise RuntimeError("سقف ساعتی جلسهٔ مرورگر پر شده است.")
    if _playwright_hits and now - _playwright_hits[-1] < settings.social_playwright_min_seconds:
        raise RuntimeError("فاصلهٔ درخواست‌های مرورگر رعایت نشده است.")
    _playwright_hits.append(now)


def _cookies() -> list[dict[str, Any]]:
    raw = settings.social_session_cookies.strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise RuntimeError("SOCIAL_SESSION_COOKIES باید یک فهرست JSON باشد.")
    return parsed


def _search_url(network: str, query: str, kind: str) -> str:
    from urllib.parse import quote_plus

    text = quote_plus(query.strip())
    if network == "linkedin":
        base = (
            "https://www.linkedin.com/search/results/people/"
            if kind == "person"
            else ("https://www.linkedin.com/search/results/companies/")
        )
        return f"{base}?keywords={text}"
    return f"https://www.facebook.com/search/pages?q={text}"


def social_provider() -> SocialProvider:
    if settings.social_playwright_enabled and settings.social_session_cookies.strip():
        return PlaywrightSessionProvider()
    return PublicWebProvider()


def _render(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "نتیجه‌ای از صفحات عمومی پیدا نشد."
    lines = []
    for row in rows:
        bits = [row["name"] or "بدون نام"]
        if row["location"]:
            bits.append(row["location"])
        if row["website"]:
            bits.append(row["website"])
        if row["emails"]:
            bits.append("ایمیل: " + "، ".join(row["emails"]))
        if row["phones"]:
            bits.append("تلفن: " + "، ".join(row["phones"]))
        if row["url"]:
            bits.append(row["url"])
        lines.append("- " + " | ".join(bits))
    return "\n".join(lines)


def run_social_search(network: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return ToolResult(ok=False, content="عبارت جست‌وجو لازم است.")
    kind = str(arguments.get("kind") or "company")
    limit = max(1, min(int(arguments.get("limit") or 5), 8))
    note_progress(context, f"جست‌وجوی {network} شروع شد", query=query, network=network)
    provider = social_provider()
    try:
        rows = provider.search(network=network, query=query, kind=kind, limit=limit)
    except Exception as exc:
        note_progress(context, f"جست‌وجوی {network} ناموفق بود", network=network, ok=False)
        return ToolResult(ok=False, content=str(exc) or f"جست‌وجوی {network} ناموفق بود.")
    note_progress(context, f"{len(rows)} نتیجه از {network}", network=network, count=len(rows))
    saved = 0
    if arguments.get("save") and context.db is not None:
        saved = _save_rows(network, rows, context)
    content = _render(rows)
    if saved:
        content += f"\n{saved} سرنخ با منبع {network} ذخیره شد."
    return ToolResult(
        ok=True, content=content, data={"results": rows, "saved": saved, "provider": provider.name}
    )


def _save_rows(network: str, rows: list[dict[str, Any]], context: ToolContext) -> int:
    from app.tools.actions import CreateLeadTool

    tool = CreateLeadTool()
    party = "supplier" if context.agent_slug in {"research", "consulting"} else "customer"
    saved = 0
    for row in rows:
        if not row.get("name"):
            continue
        result = tool.execute(
            {
                "company_name": row["name"],
                "title": f"{network}: {row['name']}",
                "city": row.get("location") or "",
                "website": row.get("website") or "",
                "email": (row.get("emails") or [""])[0],
                "phone": (row.get("phones") or [""])[0],
                "notes": row.get("snippet") or "",
                "source": network,
                "party": party,
            },
            context,
        )
        if result.ok:
            saved += 1
    return saved


class LinkedInSearchTool(Tool):
    name = "linkedin_search"
    description = (
        "جست‌وجوی شرکت یا شخص در لینکدین از راه نتایج عمومی وب (site:linkedin.com). "
        "نام، وب‌سایت، موقعیت و نشانهٔ تماس را استخراج می‌کند."
    )
    provider = "searxng"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "kind": {"type": "string", "enum": ["company", "person"]},
            "limit": {"type": "integer"},
            "save": {"type": "boolean"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        return run_social_search("linkedin", arguments, context)


class FacebookSearchTool(Tool):
    name = "facebook_search"
    description = (
        "جست‌وجوی صفحهٔ عمومی فیسبوک با site:facebook.com و استخراج نام، موقعیت و نشانهٔ تماس."
    )
    provider = "searxng"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "save": {"type": "boolean"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        return run_social_search("facebook", arguments, context)
