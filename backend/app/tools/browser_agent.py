"""Autonomous browser. Playwright in the worker, a static page driver in tests."""

from __future__ import annotations

import base64
import logging
import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

BROWSER_TOOL_NAMES = (
    "open_url",
    "browser_click",
    "browser_type",
    "browser_select",
    "browser_scroll",
    "browser_extract",
    "browser_screenshot",
    "browser_fill_form",
    "browser_wait",
    "browser_back",
)

_IRREVERSIBLE = (
    "submit",
    "send",
    "login",
    "sign in",
    "pay",
    "buy",
    "purchase",
    "checkout",
    "ورود",
    "ارسال",
    "خرید",
    "پرداخت",
    "ثبت",
)

# 1x1 jpeg
_TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxISEhUQEhIVFhUVFRUVFRUVFRUWFxUVFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMtNygtLisBCgoKDg0OGhAQGy0lHyUtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBIgACEQEDEQH/xAAbAAABBQEBAAAAAAAAAAAAAAADAAIEBQYBB//EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAGgH//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAT8Af//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8Af//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQMBAT8Af//Z"
)

_sessions: dict[str, PageDriver] = {}
_steps: dict[str, int] = {}


class PageDriver:
    url: str = ""

    def open(self, url: str) -> None:
        raise NotImplementedError

    def elements(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def click(self, index: int) -> str:
        raise NotImplementedError

    def type_text(self, index: int, text: str) -> str:
        raise NotImplementedError

    def select(self, index: int, value: str) -> str:
        raise NotImplementedError

    def scroll(self, direction: str) -> str:
        return f"scroll {direction}"

    def extract(self) -> dict[str, Any]:
        raise NotImplementedError

    def screenshot(self) -> bytes:
        return _TINY_JPEG

    def fill(self, fields: dict[str, str]) -> str:
        raise NotImplementedError

    def wait_for(self, text: str) -> str:
        body = self.extract().get("text") or ""
        if text and text not in body:
            raise RuntimeError("متن مورد انتظار روی صفحه نیست.")
        return "صفحه آماده است."

    def back(self) -> str:
        raise NotImplementedError

    def element(self, index: int) -> dict[str, Any]:
        rows = self.elements()
        if index < 1 or index > len(rows):
            raise RuntimeError("شماره عنصر در فهرست صفحه نیست.")
        return rows[index - 1]


class _StaticParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, Any]] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag not in {"a", "button", "input", "select", "textarea"}:
            return
        label = (
            data.get("aria-label")
            or data.get("placeholder")
            or data.get("value")
            or data.get("name")
            or ""
        )
        if tag == "a":
            label = label or data.get("href") or "link"
        self.elements.append(
            {
                "tag": tag,
                "role": "link" if tag == "a" else "button" if tag == "button" else "input",
                "name": label,
                "href": data.get("href") or "",
                "type": data.get("type") or "",
                "value": data.get("value") or "",
            }
        )

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


class StaticPage(PageDriver):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.url = ""
        self.path = root / "index.html"
        self.history: list[Path] = []
        self.values: dict[int, str] = {}
        self._load(self.path)

    def _load(self, path: Path) -> None:
        parser = _StaticParser()
        parser.feed(path.read_text(encoding="utf-8"))
        self.elements_cache = parser.elements
        self.text = "\n".join(parser.parts)
        # Attach following text to anchors when the label was only the href.
        self.path = path
        self.url = f"static://{path.name}"

    def open(self, url: str) -> None:
        name = url.split("/")[-1] or "index.html"
        path = (self.root / name).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise RuntimeError("صفحه خارج از ریشهٔ آزمون است.")
        if not path.is_file():
            raise RuntimeError("صفحه پیدا نشد.")
        if self.path:
            self.history.append(self.path)
        self.values = {}
        self._load(path)

    def elements(self) -> list[dict[str, Any]]:
        rows = []
        for index, row in enumerate(self.elements_cache, start=1):
            item = dict(row)
            item["index"] = index
            if index in self.values:
                item["value"] = self.values[index]
            rows.append(item)
        return rows

    def click(self, index: int) -> str:
        row = self.element(index)
        href = row.get("href") or ""
        if href:
            self.open(href)
            return f"رفت به {self.url}"
        return f"کلیک روی {row.get('name')}"

    def type_text(self, index: int, text: str) -> str:
        self.element(index)
        self.values[index] = text
        return "متن وارد شد."

    def select(self, index: int, value: str) -> str:
        self.element(index)
        self.values[index] = value
        return "گزینه انتخاب شد."

    def extract(self) -> dict[str, Any]:
        links = [
            {"index": row["index"], "text": row["name"], "href": row["href"]}
            for row in self.elements()
            if row.get("href")
        ]
        return {"url": self.url, "text": self.text, "links": links}

    def fill(self, fields: dict[str, str]) -> str:
        for row in self.elements():
            if row.get("name") in fields:
                self.values[row["index"]] = fields[row["name"]]
        return "فرم پر شد."

    def back(self) -> str:
        if not self.history:
            return "تاریخچه‌ای نیست."
        self._load(self.history.pop())
        return f"برگشت به {self.url}"


class PlaywrightPage(PageDriver):
    def __init__(self, profile: Path, proxy: str) -> None:
        from playwright.sync_api import sync_playwright

        profile.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        kwargs: dict[str, Any] = {"headless": True}
        if proxy:
            kwargs["proxy"] = {"server": proxy}
        self._context = self._playwright.chromium.launch_persistent_context(str(profile), **kwargs)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self.url = ""

    def open(self, url: str) -> None:
        self._page.goto(url, timeout=25000, wait_until="domcontentloaded")
        self.url = self._page.url

    def elements(self) -> list[dict[str, Any]]:
        raw = self._page.evaluate(
            """() => {
                const nodes = Array.from(document.querySelectorAll('a,button,input,select,textarea'));
                return nodes.slice(0, 40).map((node) => ({
                    tag: node.tagName.toLowerCase(),
                    role: node.getAttribute('role') || node.tagName.toLowerCase(),
                    name: (node.getAttribute('aria-label') || node.innerText || node.getAttribute('placeholder') || node.getAttribute('name') || '').trim().slice(0, 80),
                    href: node.getAttribute('href') || '',
                    type: node.getAttribute('type') || '',
                }));
            }"""
        )
        return [{"index": index, **row} for index, row in enumerate(raw, start=1)]

    def click(self, index: int) -> str:
        self._locator(index).click(timeout=8000)
        self.url = self._page.url
        return f"کلیک شد. نشانی: {self.url}"

    def type_text(self, index: int, text: str) -> str:
        self._locator(index).fill(text, timeout=8000)
        return "متن وارد شد."

    def select(self, index: int, value: str) -> str:
        self._locator(index).select_option(value, timeout=8000)
        return "گزینه انتخاب شد."

    def scroll(self, direction: str) -> str:
        delta = -500 if direction == "up" else 500
        self._page.mouse.wheel(0, delta)
        return "صفحه جابه‌جا شد."

    def extract(self) -> dict[str, Any]:
        text = self._page.inner_text("body")[:6000]
        links = [
            {"index": row["index"], "text": row["name"], "href": row["href"]}
            for row in self.elements()
            if row.get("href")
        ]
        return {"url": self._page.url, "text": text, "links": links}

    def screenshot(self) -> bytes:
        return self._page.screenshot(type="jpeg", quality=40, full_page=False)

    def fill(self, fields: dict[str, str]) -> str:
        for row in self.elements():
            if row.get("name") in fields:
                self.type_text(row["index"], fields[row["name"]])
        return "فرم پر شد."

    def wait_for(self, text: str) -> str:
        self._page.get_by_text(text).first.wait_for(timeout=8000)
        return "صفحه آماده است."

    def back(self) -> str:
        self._page.go_back(timeout=8000)
        self.url = self._page.url
        return f"برگشت به {self.url}"

    def _locator(self, index: int):
        self.element(index)
        return self._page.locator("a,button,input,select,textarea").nth(index - 1)


def session_for(context: ToolContext) -> PageDriver:
    key = context.user_id or context.task_id or "shared"
    existing = _sessions.get(key)
    if existing is not None:
        return existing
    backend = (settings.browser_backend or "").strip().lower()
    if backend == "static":
        root = Path(settings.browser_static_root or "tests/fixtures/browser")
        page: PageDriver = StaticPage(root)
    else:
        proxy = (
            settings.browser_proxy.strip()
            or settings.https_proxy.strip()
            or os.environ.get("HTTPS_PROXY", "")
        )
        profile = Path(settings.browser_profile_dir) / (context.user_id or "shared")
        page = PlaywrightPage(profile, proxy)
    _sessions[key] = page
    return page


def reset_sessions() -> None:
    _sessions.clear()
    _steps.clear()


def _blocked(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    blocked = [
        item.strip().lower() for item in settings.browser_blocked_domains.split(",") if item.strip()
    ]
    return any(host == item or host.endswith(f".{item}") for item in blocked)


def _social_limit(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if "linkedin.com" in host or "facebook.com" in host:
        from app.tools.social import reserve_playwright_slot

        reserve_playwright_slot()


def _secret_values() -> list[str]:
    values = [
        settings.smtp_password,
        settings.imap_password,
        settings.openai_api_key,
        settings.anthropic_api_key,
        settings.gemini_api_key,
        settings.openrouter_api_key,
        settings.telegram_bot_token,
        settings.whatsapp_token,
        settings.kavenegar_api_key,
        settings.social_session_cookies,
    ]
    return [item.strip() for item in values if item and len(item.strip()) >= 8]


def _contains_secret(text: str) -> bool:
    for secret in _secret_values():
        if secret in text:
            return True
    return False


def _irreversible(label: str) -> bool:
    folded = (label or "").lower()
    return any(word in folded for word in _IRREVERSIBLE)


def _confirm(context: ToolContext, summary: str) -> ToolResult | None:
    if context.db is None:
        return ToolResult(ok=False, approval_required=True, content=f"نیاز به تأیید: {summary}")
    from langgraph.errors import GraphInterrupt

    from app.runtime.gates import run_gated_tool

    class _Gate(Tool):
        name = "browser_confirm"
        description = "تأیید اقدام برگشت‌ناپذیر مرورگر"
        action_type = "browser"
        input_schema: dict[str, Any] = {"type": "object", "properties": {}}

        def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
            return ToolResult(ok=True, content="ok")

    try:
        result = run_gated_tool(
            _Gate(),
            {"summary": summary, "to": "browser", "body": summary},
            context,
            call_id=f"browser:{summary[:40]}",
        )
    except GraphInterrupt:
        raise
    except Exception:
        return ToolResult(ok=False, approval_required=True, content=f"نیاز به تأیید: {summary}")
    if not result.ok:
        return result
    return None


def _budget(context: ToolContext) -> ToolResult | None:
    key = context.task_id or context.user_id or "shared"
    used = _steps.get(key, 0) + 1
    _steps[key] = used
    if used > max(1, settings.browser_max_steps):
        return ToolResult(ok=False, content="سقف گام‌های مرورگر این وظیفه پر شده است.")
    return None


def _emit(context: ToolContext, kind: str, payload: dict[str, Any]) -> None:
    if context.db is None or not context.task_id:
        return
    from app.runtime.events import emit_event

    emit_event(context.db, context.task_id, kind, payload)


def _describe(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "عنصر تعاملی پیدا نشد."
    lines = []
    for row in rows[:40]:
        lines.append(
            f"[{row['index']}] {row.get('role') or row.get('tag')} {row.get('name') or ''} {row.get('href') or ''}".strip()
        )
    return "\n".join(lines)


def _after(context: ToolContext, page: PageDriver, action: str) -> ToolResult:
    rows = page.elements()
    shot = base64.b64encode(page.screenshot()).decode("ascii")
    _emit(context, "browser.action", {"action": action, "url": page.url})
    _emit(context, "browser.screenshot", {"image": shot, "url": page.url})
    return ToolResult(
        ok=True,
        content=f"{action}\n{page.url}\n{_describe(rows)}",
        data={"url": page.url, "elements": rows, "image": shot},
    )


class OpenUrlTool(Tool):
    name = "open_url"
    description = "باز کردن یک نشانی و برگرداندن فهرست شماره‌دار عنصرهای قابل کلیک."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        url = str(arguments.get("url") or "").strip()
        if _blocked(url):
            return ToolResult(ok=False, content="این دامنه در فهرست ممنوع مرورگر است.")
        limited = _budget(context)
        if limited:
            return limited
        try:
            _social_limit(url)
            page = session_for(context)
            page.open(url)
        except Exception as exc:
            return ToolResult(ok=False, content=f"باز کردن صفحه ناموفق بود: {exc}")
        return _after(context, page, f"باز شد {url}")


class ClickTool(Tool):
    name = "browser_click"
    description = "کلیک روی عنصر با شمارهٔ فهرست دسترس‌پذیری."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {"index": {"type": "integer"}},
        "required": ["index"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        page = session_for(context)
        index = int(arguments.get("index") or 0)
        try:
            row = page.element(index)
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        label = f"{row.get('name')} {row.get('type')} {row.get('href')}"
        if _irreversible(label):
            denied = _confirm(context, f"کلیک روی {row.get('name') or index}")
            if denied:
                return denied
        try:
            note = page.click(index)
        except Exception as exc:
            return ToolResult(ok=False, content=f"کلیک ناموفق بود: {exc}")
        return _after(context, page, note)


class TypeTool(Tool):
    name = "browser_type"
    description = "نوشتن در یک فیلد با شمارهٔ فهرست. رمزهای محیطی نوشته نمی‌شوند."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {"index": {"type": "integer"}, "text": {"type": "string"}},
        "required": ["index", "text"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        text = str(arguments.get("text") or "")
        if _contains_secret(text):
            return ToolResult(ok=False, content="نوشتن راز محیطی در مرورگر مجاز نیست.")
        page = session_for(context)
        index = int(arguments.get("index") or 0)
        try:
            row = page.element(index)
            if str(row.get("type") or "").lower() == "password":
                denied = _confirm(context, "ورود رمز در فرم")
                if denied:
                    return denied
            note = page.type_text(index, text)
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        return _after(context, page, note)


class SelectTool(Tool):
    name = "browser_select"
    description = "انتخاب یک گزینه در فهرست کشویی."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {"index": {"type": "integer"}, "value": {"type": "string"}},
        "required": ["index", "value"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        page = session_for(context)
        try:
            note = page.select(int(arguments.get("index") or 0), str(arguments.get("value") or ""))
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        return _after(context, page, note)


class ScrollTool(Tool):
    name = "browser_scroll"
    description = "جابه‌جایی صفحه به بالا یا پایین."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {"direction": {"type": "string"}},
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        page = session_for(context)
        note = page.scroll(str(arguments.get("direction") or "down"))
        return _after(context, page, note)


class ExtractTool(Tool):
    name = "browser_extract"
    description = "متن خوانا و پیوندهای صفحهٔ جاری."
    provider = "playwright"
    input_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        page = session_for(context)
        data = page.extract()
        _emit(context, "browser.action", {"action": "extract", "url": page.url})
        lines = [data.get("text") or ""]
        for link in data.get("links") or []:
            lines.append(f"- {link.get('text')}: {link.get('href')}")
        return ToolResult(ok=True, content="\n".join(lines)[:6000], data=data)


class ScreenshotTool(Tool):
    name = "browser_screenshot"
    description = "عکس کوچک از صفحهٔ جاری."
    provider = "playwright"
    input_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        page = session_for(context)
        return _after(context, page, "عکس صفحه")


class FillFormTool(Tool):
    name = "browser_fill_form"
    description = "پر کردن فرم. ارسال فرم نیاز به تأیید دارد."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {
            "fields": {"type": "object"},
            "submit": {"type": "boolean"},
        },
        "required": ["fields"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        fields = arguments.get("fields") or {}
        if not isinstance(fields, dict):
            return ToolResult(ok=False, content="fields باید شیء باشد.")
        blob = " ".join(str(value) for value in fields.values())
        if _contains_secret(blob):
            return ToolResult(ok=False, content="نوشتن راز محیطی در مرورگر مجاز نیست.")
        if arguments.get("submit"):
            denied = _confirm(context, "ارسال فرم")
            if denied:
                return denied
        page = session_for(context)
        try:
            note = page.fill({str(key): str(value) for key, value in fields.items()})
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        return _after(context, page, note)


class WaitTool(Tool):
    name = "browser_wait"
    description = "منتظر ماندن تا یک متن روی صفحه دیده شود."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        page = session_for(context)
        try:
            note = page.wait_for(str(arguments.get("text") or ""))
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        return _after(context, page, note)


class BackTool(Tool):
    name = "browser_back"
    description = "برگشت به صفحهٔ قبلی."
    provider = "playwright"
    input_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        limited = _budget(context)
        if limited:
            return limited
        page = session_for(context)
        try:
            note = page.back()
        except Exception as exc:
            return ToolResult(ok=False, content=str(exc))
        return _after(context, page, note)


def browser_tools() -> list[Tool]:
    return [
        OpenUrlTool(),
        ClickTool(),
        TypeTool(),
        SelectTool(),
        ScrollTool(),
        ExtractTool(),
        ScreenshotTool(),
        FillFormTool(),
        WaitTool(),
        BackTool(),
    ]
