"""Built-in agent plugins. Drop a module that exports SPEC to add another."""

from app.agents.registry import load_package

load_package("app.agents.catalog")
