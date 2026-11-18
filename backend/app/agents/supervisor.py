from __future__ import annotations

# First match wins. Keep more specific commercial intents ahead of research.
_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("lead_generation", ("لید", "مشتری‌یابی", "مشتری یابی", "سرنخ", "lead", "prospect")),
    (
        "sales_negotiation",
        ("مذاکره", "تخفیف", "پیشنهاد قیمت", "negotiat", "discount", "quote"),
    ),
    ("consulting", ("تجاری‌سازی", "تجاری سازی", "طراحی محصول", "consult", "commercial")),
    ("research", ("تحقیق", "بازار", "رقیب", "research", "market")),
)


def route_task(text: str, explicit_slug: str | None = None) -> str:
    """Pick a specialist. An explicit slug from the user always wins.

    The keyword table is the skeleton router. A later version can call the
    fast model tier for ambiguous tasks; the graph node should keep using
    this function so both entry points stay aligned.
    """
    slug = (explicit_slug or "").strip()
    if slug:
        return slug
    haystack = text or ""
    lowered = haystack.lower()
    for candidate, keys in _ROUTES:
        if any(key in haystack or key in lowered for key in keys):
            return candidate
    return "research"
