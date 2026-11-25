"""Browser tools against a local static page, plus safety limits."""

from pathlib import Path

from app.config import settings
from app.tools.base import ToolContext, tool_registry
from app.tools.browser_agent import reset_sessions

ROOT = Path(__file__).parent / "fixtures" / "browser"


def setup_function() -> None:
    reset_sessions()
    settings.browser_backend = "static"
    settings.browser_static_root = str(ROOT)
    settings.browser_max_steps = 40
    settings.browser_blocked_domains = ""


def _tool(name: str):
    return tool_registry.get(name)


def test_open_extract_and_click_local_page():
    context = ToolContext()
    opened = _tool("open_url").execute({"url": "static://index.html"}, context)
    assert opened.ok
    assert "کارخانه نمونه" in opened.content or any(
        "درباره" in (item.get("name") or "") or item.get("href") == "about.html"
        for item in opened.data["elements"]
    )
    extracted = _tool("browser_extract").execute({}, context)
    assert "مبلمان" in extracted.content
    clicked = _tool("browser_click").execute({"index": 1}, context)
    assert clicked.ok
    assert "about.html" in clicked.content
    again = _tool("browser_extract").execute({}, context)
    assert "درباره کارخانه" in again.content


def test_blocked_domain_and_step_limit(monkeypatch):
    monkeypatch.setattr(settings, "browser_blocked_domains", "evil.test")
    context = ToolContext()
    blocked = _tool("open_url").execute({"url": "https://evil.test/form"}, context)
    assert blocked.ok is False
    assert "ممنوع" in blocked.content
    monkeypatch.setattr(settings, "browser_blocked_domains", "")
    monkeypatch.setattr(settings, "browser_max_steps", 1)
    assert _tool("open_url").execute({"url": "static://index.html"}, context).ok
    limited = _tool("browser_scroll").execute({"direction": "down"}, context)
    assert limited.ok is False
    assert "سقف" in limited.content


def test_submit_requires_approval_and_secrets_are_refused(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-secret-value")
    context = ToolContext()
    _tool("open_url").execute({"url": "static://index.html"}, context)
    typed = _tool("browser_type").execute({"index": 2, "text": "sk-test-secret-value"}, context)
    assert typed.ok is False
    assert "راز" in typed.content
    clicked = _tool("browser_click").execute({"index": 3}, context)
    assert clicked.approval_required
    assert "تأیید" in clicked.content
