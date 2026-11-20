from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.runtime.graph import clean_tool_text, trim_tool_history


def test_worker_module_registers_lead_generation_tools() -> None:
    root = Path(__file__).resolve().parents[1]
    code = """
import app.worker.main
from app.agents.registry import registry
from app.runtime.graph import _schemas

spec = registry.get("lead_generation")
schemas = _schemas(list(spec.allowed_tools))
names = {item["function"]["name"] for item in schemas}
assert schemas, spec.allowed_tools
assert "web_search" in names
assert "create_lead" in names
print(len(schemas))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_tool_text_is_cleaned_and_capped() -> None:
    raw = "ok\x00\x07" + ("الف" * 7000) + chr(0xD800)
    cleaned = clean_tool_text(raw, limit=6000)
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\ud800" not in cleaned
    assert cleaned.endswith("\n[truncated]")
    assert len(cleaned) <= 6000 + len("\n[truncated]")


def test_older_tool_messages_are_trimmed() -> None:
    messages = [
        {"role": "user", "content": "هدف"},
        {"role": "tool", "tool_call_id": "1", "content": "قدیمی " * 800},
        {"role": "tool", "tool_call_id": "2", "content": "تازه"},
    ]
    trimmed = trim_tool_history(messages, budget=1000)
    assert trimmed[0]["content"] == "هدف"
    assert trimmed[1]["content"].endswith("\n[truncated]")
    assert len(trimmed[1]["content"]) < len(messages[1]["content"])
    assert trimmed[2]["content"] == messages[2]["content"]
