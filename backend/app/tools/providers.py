from __future__ import annotations

from typing import Protocol


class SearchProvider(Protocol):
    def search(self, query: str, limit: int = 5) -> list[dict]: ...


class FetchProvider(Protocol):
    def fetch(self, url: str) -> dict: ...


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> dict: ...


class CrmProvider(Protocol):
    def lookup(self, query: str) -> dict: ...


class StubSearchProvider:
    """Placeholder. Swap via `set_search_provider` for a real search API."""

    def search(self, query: str, limit: int = 5) -> list[dict]:
        return [
            {
                "title": f"نتیجهٔ آزمایشی برای «{query}»",
                "url": "https://example.com/search",
                "snippet": "این نتیجه ساختگی است. ارائه‌دهندهٔ واقعی جست‌وجو را جایگزین StubSearchProvider کنید.",
            }
        ][:limit]


class StubFetchProvider:
    def fetch(self, url: str) -> dict:
        return {
            "url": url,
            "status_code": 200,
            "title": "صفحهٔ آزمایشی",
            "text": (
                f"محتوای ساختگی برای {url}. "
                "پیاده‌سازی واقعی پشت FetchProvider قرار می‌گیرد و هنوز صفحه‌ای را دانلود نمی‌کند."
            ),
        }


class StubEmailProvider:
    """Not used until an approval is executed, and even then the worker only logs."""

    def send(self, *, to: str, subject: str, body: str) -> dict:
        return {"delivered": False, "provider": "stub", "to": to, "subject": subject, "body": body}


class StubCrmProvider:
    def lookup(self, query: str) -> dict:
        return {
            "provider": "placeholder",
            "query": query,
            "contacts": [],
            "note": "اتصال CRM هنوز پیاده‌سازی نشده است.",
        }


_search: SearchProvider = StubSearchProvider()
_fetch: FetchProvider = StubFetchProvider()
_email: EmailProvider = StubEmailProvider()
_crm: CrmProvider = StubCrmProvider()


def get_search_provider() -> SearchProvider:
    return _search


def set_search_provider(provider: SearchProvider) -> None:
    global _search
    _search = provider


def get_fetch_provider() -> FetchProvider:
    return _fetch


def set_fetch_provider(provider: FetchProvider) -> None:
    global _fetch
    _fetch = provider


def get_email_provider() -> EmailProvider:
    return _email


def set_email_provider(provider: EmailProvider) -> None:
    global _email
    _email = provider


def get_crm_provider() -> CrmProvider:
    return _crm


def set_crm_provider(provider: CrmProvider) -> None:
    global _crm
    _crm = provider
