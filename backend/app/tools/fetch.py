"""Fetch and clean a page. Playwright is used only by the browser tool."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def fetch_page(url: str) -> dict:
    with httpx.Client(timeout=25, trust_env=True, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "IRHub/0.1"})
        response.raise_for_status()
        raw = response.text[:1_000_000]
        final_url = str(response.url)
    text = _clean(raw, final_url)
    title = _title(raw)
    return {"url": final_url, "title": title, "text": text[:12000], "status_code": 200}


def _clean(html: str, url: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(html, url=url, include_comments=False, include_tables=True)
        if extracted and extracted.strip():
            return extracted.strip()
    except Exception:
        logger.exception("trafilatura failed")
    text, _title_text = _plain(html)
    return text[:12000]


def _title(html: str) -> str:
    _text, title = _plain(html)
    return title


def _plain(html: str) -> tuple[str, str]:
    from html.parser import HTMLParser

    class Extractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self.title_parts: list[str] = []
            self.skip = 0
            self.in_title = False

        def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
            if tag in {"script", "style", "noscript"}:
                self.skip += 1
            if tag == "title":
                self.in_title = True

        def handle_endtag(self, tag: str) -> None:
            if tag in {"script", "style", "noscript"} and self.skip:
                self.skip -= 1
            if tag == "title":
                self.in_title = False

        def handle_data(self, data: str) -> None:
            if self.in_title:
                self.title_parts.append(data)
            elif not self.skip:
                self.parts.append(data)

    parser = Extractor()
    parser.feed(html)
    text = " ".join(" ".join(parser.parts).split())
    title = " ".join(parser.title_parts).strip()
    return text, title
