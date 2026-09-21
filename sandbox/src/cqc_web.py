from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urlparse

import httpx

from sandbox.src.certificate_fields import CertificateFieldExtractor
from sandbox.src.errors import CqcWebFetchError
from sandbox.src.schemas import CccCertificateFields

CQC_HOST_SUFFIXES = ("cqc.com.cn", "cqccms.com.cn")
FETCH_TIMEOUT_SECONDS = 15.0
USER_AGENT = (
    "Mozilla/5.0 (compatible; DocumentVerificationAgent/1.0; +https://www.cqc.com.cn)"
)
MIN_PAGE_TEXT_LENGTH = 40


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "td", "th"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in {"p", "div", "tr", "li", "table"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        joined = " ".join(self._parts)
        joined = re.sub(r"[ \t]+\n", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return re.sub(r"[ \t]{2,}", " ", joined).strip()


class CqcFieldExtractor(Protocol):
    def extract_from_web(self, page_text: str) -> CccCertificateFields: ...


def select_cqc_url(qr_payloads: list[str]) -> str | None:
    """Return the first allowed CQC HTTP(S) URL from ordered QR payloads."""
    for payload in qr_payloads:
        url = payload.strip()
        if not _is_http_url(url):
            continue
        if _is_allowed_cqc_host(url):
            return url
    return None


def fetch_page_text(url: str, client: httpx.Client | None = None) -> str:
    """Fetch a CQC page and return normalized visible text."""
    if not _is_allowed_cqc_host(url):
        raise CqcWebFetchError(f"Blocked non-CQC URL: {url}")

    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        response = http_client.get(url)
        response.raise_for_status()
        text = html_to_text(response.text)
        if len(text) < MIN_PAGE_TEXT_LENGTH:
            raise CqcWebFetchError(
                "The CQC page did not contain enough readable certificate text."
            )
        return text
    except httpx.HTTPError as exc:
        raise CqcWebFetchError(f"Unable to fetch CQC page: {exc}") from exc
    finally:
        if owns_client:
            http_client.close()


def html_to_text(html: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def extract_web_certificate_fields(
    page_text: str,
    field_extractor: CertificateFieldExtractor,
) -> CccCertificateFields:
    return field_extractor.extract_from_web(page_text)


def fetch_cqc_certificate_from_qr(
    qr_payloads: list[str],
    field_extractor: CertificateFieldExtractor | None,
) -> tuple[CccCertificateFields | None, str | None]:
    """Fetch and parse the preferred CQC QR URL into certificate JSON."""
    url = select_cqc_url(qr_payloads)
    if url is None:
        return None, None
    if field_extractor is None:
        return None, "CQC website extraction is unavailable."

    try:
        page_text = fetch_page_text(url)
        certificate = extract_web_certificate_fields(page_text, field_extractor)
        return certificate, None
    except CqcWebFetchError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, f"{exc.__class__.__name__}: {exc}"


def _is_http_url(payload: str) -> bool:
    lowered = payload.strip().lower()
    return lowered.startswith(("http://", "https://"))


def _is_allowed_cqc_host(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return False
    lowered = host.lower()
    return any(
        lowered == suffix or lowered.endswith(f".{suffix}")
        for suffix in CQC_HOST_SUFFIXES
    )
