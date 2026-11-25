from __future__ import annotations

import importlib
import pkgutil
import re
from dataclasses import dataclass

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True)
class AgentSpec:
    """Code-side plugin definition. The database row is the runtime config.

    Panel edits win after the first seed. Adding an agent later is a new
    module under `app/agents/catalog` that exports `SPEC`, or a row created
    from the admin panel (no code module required).
    """

    slug: str
    name: str
    name_fa: str
    description: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    model_strong: str
    model_fast: str
    temperature: float = 0.3


class AgentRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        if not SLUG_RE.match(spec.slug):
            raise ValueError(f"slug must match ^[a-z][a-z0-9_]{{1,63}}$ (got {spec.slug!r})")
        if spec.slug in self._specs:
            raise ValueError(f"agent already registered: {spec.slug}")
        if not spec.system_prompt.strip():
            raise ValueError("system prompt is required")
        if not spec.name.strip() or not spec.name_fa.strip():
            raise ValueError("name is required")
        self._specs[spec.slug] = spec

    def get(self, slug: str) -> AgentSpec:
        try:
            return self._specs[slug]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {slug}") from exc

    def list(self) -> list[AgentSpec]:
        return [self._specs[slug] for slug in sorted(self._specs)]

    def slugs(self) -> set[str]:
        return set(self._specs)


registry = AgentRegistry()


def load_package(package_name: str, reg: AgentRegistry | None = None) -> list[str]:
    """Register every submodule that exports an `AgentSpec` named SPEC."""
    target = registry if reg is None else reg
    package = importlib.import_module(package_name)
    loaded: list[str] = []
    existing = target.slugs()
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package_name}.{info.name}")
        spec = getattr(module, "SPEC", None)
        if not isinstance(spec, AgentSpec) or spec.slug in existing:
            continue
        target.register(spec)
        existing.add(spec.slug)
        loaded.append(spec.slug)
    return loaded
