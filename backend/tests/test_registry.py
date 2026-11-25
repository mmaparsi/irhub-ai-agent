from __future__ import annotations

import app.agents.catalog  # noqa: F401
import app.tools.builtin  # noqa: F401
from app.agents.graph import build_supervisor_graph
from app.agents.registry import AgentRegistry, AgentSpec
from app.agents.supervisor import route_task
from app.tools.base import ToolContext, tool_registry
from app.tools.providers import StubSearchProvider, set_search_provider


def _spec(slug: str = "demo_agent") -> AgentSpec:
    return AgentSpec(
        slug=slug,
        name="Demo",
        name_fa="نمونه",
        description="test",
        system_prompt="تو یک عامل آزمایشی هستی.",
        allowed_tools=("web_search",),
        model_strong="test/strong",
        model_fast="test/fast",
    )


def test_register_get_and_reject_duplicates() -> None:
    reg = AgentRegistry()
    reg.register(_spec())
    assert reg.get("demo_agent").name_fa == "نمونه"
    try:
        reg.register(_spec())
        raise AssertionError("duplicate slug should fail")
    except ValueError:
        pass
    try:
        reg.register(_spec("Bad-Slug"))
        raise AssertionError("invalid slug should fail")
    except ValueError:
        pass
    try:
        reg.get("missing")
        raise AssertionError("missing slug should fail")
    except KeyError:
        pass


def test_builtin_agents_and_tools() -> None:
    slugs = {
        spec.slug
        for spec in __import__("app.agents.registry", fromlist=["registry"]).registry.list()
    }
    assert {"research", "lead_generation", "sales_negotiation", "consulting"} <= slugs
    names = set(tool_registry.names())
    for spec in __import__("app.agents.registry", fromlist=["registry"]).registry.list():
        assert spec.system_prompt.strip()
        assert set(spec.allowed_tools) <= names


def test_route_task_keywords_and_explicit_slug() -> None:
    assert route_task("چند سرنخ برای ورق فولاد پیدا کن") == "lead_generation"
    assert route_task("تخفیف این پیشنهاد قیمت چقدر باشد؟") == "sales_negotiation"
    assert route_task("مسیر تجاری‌سازی محصول جدید") == "consulting"
    assert route_task("تحقیق بازار رقبا") == "research"
    assert route_task("سلام", "consulting") == "consulting"
    assert route_task("سلام") == "research"


def test_supervisor_graph_delegates_to_one_specialist() -> None:
    def specialist(state):
        return {"result": f"ran:{state['agent_slug']}"}

    graph = build_supervisor_graph(specialist)
    routed = graph.invoke({"task": "لیست سرنخ مشتریان صنعتی"})
    assert routed["agent_slug"] == "lead_generation"
    assert routed["result"] == "ran:lead_generation"
    explicit = graph.invoke({"task": "hello", "agent_slug": "consulting"})
    assert explicit["agent_slug"] == "consulting"


def test_tool_is_mcp_shaped_and_provider_is_swappable() -> None:
    tool = tool_registry.get("web_search")
    described = tool.to_mcp_tool()
    assert described["name"] == "web_search"
    assert "inputSchema" in described

    class FakeSearch:
        def search(self, query: str, limit: int = 5) -> list[dict]:
            return [{"title": "عنوان", "url": "https://example.com", "snippet": query}]

    set_search_provider(FakeSearch())
    try:
        result = tool.execute({"query": "ورق گالوانیزه"}, ToolContext())
    finally:
        set_search_provider(StubSearchProvider())
    assert result.ok
    assert "ورق گالوانیزه" in result.content
