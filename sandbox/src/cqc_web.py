from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import httpx

from sandbox.src.certificate_fields import CertificateFieldExtractor
from sandbox.src.errors import CqcWebFetchError
from sandbox.src.schemas import CccCertificateFields

CQC_HOST_SUFFIXES = ("cqc.com.cn", "cqccms.com.cn")
CERTIFICATE_QUERY_KEYS = (
    "certno",
    "certi",
    "certid",
    "certificate",
    "id",
    "no",
)
FETCH_TIMEOUT_SECONDS = 15.0
USER_AGENT = (
    "Mozilla/5.0 (compatible; DocumentVerificationAgent/1.0; +https://www.cqc.com.cn)"
)
MIN_PAGE_TEXT_LENGTH = 40
VISIBLE_TEXT_KEY = "_visible_text"


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


class _HtmlTableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row_cells: list[str] = []
        self.pairs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "table":
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._row_cells = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if self._in_cell and tag in {"td", "th"}:
            self._row_cells.append(" ".join(self._cell_parts).strip())
            self._in_cell = False
            self._cell_parts = []
        elif self._in_row and tag == "tr":
            self._append_row_pairs()
            self._in_row = False
            self._row_cells = []
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._in_cell:
            return
        text = data.strip()
        if text:
            self._cell_parts.append(text)

    def _append_row_pairs(self) -> None:
        cells = [cell for cell in self._row_cells if cell]
        if len(cells) == 2:
            label, value = cells
            if label and value:
                self.pairs.append((label, value))
            return
        if len(cells) >= 2 and len(cells) % 2 == 0:
            for index in range(0, len(cells), 2):
                label = cells[index].strip()
                value = cells[index + 1].strip()
                if label and value:
                    self.pairs.append((label, value))
            return
        if len(cells) >= 2:
            label = cells[0].strip()
            value = " ".join(cells[1:]).strip()
            if label and value:
                self.pairs.append((label, value))


class _HtmlDefinitionListExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_dl = False
        self._current_term: str | None = None
        self.pairs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "dl":
            self._in_dl = True
        elif self._in_dl and tag == "dt":
            self._current_term = None
        elif self._in_dl and tag == "dd":
            self._current_term = self._current_term or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "dl":
            self._in_dl = False
            self._current_term = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._in_dl:
            return
        text = data.strip()
        if not text:
            return
        if self._current_term is None:
            self._current_term = text
            return
        if self._current_term:
            self.pairs.append((self._current_term, text))
            self._current_term = None


class CqcFieldExtractor(Protocol):
    def extract_from_web(self, page_text: str) -> CccCertificateFields: ...


def select_cqc_url(qr_payloads: list[str]) -> str | None:
    """Return the best allowed CQC HTTP(S) URL from ordered QR payloads."""
    candidates: list[tuple[int, int, str]] = []
    for index, payload in enumerate(qr_payloads):
        url = payload.strip()
        if not _is_http_url(url) or not _is_allowed_cqc_host(url):
            continue
        candidates.append((_url_rank(url), index, url))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def fetch_page_html(url: str, client: httpx.Client | None = None) -> str:
    """Fetch raw HTML from an allowed CQC URL."""
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
        return response.text
    except httpx.HTTPError as exc:
        raise CqcWebFetchError(f"Unable to fetch CQC page: {exc}") from exc
    finally:
        if owns_client:
            http_client.close()


def fetch_page_text(url: str, client: httpx.Client | None = None) -> str:
    """Fetch a CQC page and return normalized visible text."""
    html = fetch_page_html(url, client=client)
    text = page_content_for_extraction(html)
    if len(text) < MIN_PAGE_TEXT_LENGTH:
        raise CqcWebFetchError(
            "The CQC page did not contain enough readable certificate text."
        )
    return text


def html_to_text(html: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def html_to_field_map(html: str) -> dict[str, str]:
    field_map: dict[str, str] = {}
    for label, value in _collect_html_pairs(html):
        _merge_field(field_map, label, value)
    return field_map


def html_to_page_json(html: str) -> dict[str, str]:
    """Return all label-value pairs plus full visible page text from HTML."""
    field_map = html_to_field_map(html)
    visible_text = html_to_text(html)
    if visible_text:
        field_map[VISIBLE_TEXT_KEY] = visible_text
    return field_map


def page_content_for_extraction(html: str) -> str:
    """Combine table label-value pairs with visible page text for extraction."""
    field_map = html_to_field_map(html)
    page_text = html_to_text(html)
    if not field_map:
        return page_text
    field_lines = "\n".join(f"{label}: {value}" for label, value in field_map.items())
    if page_text:
        return f"{field_lines}\n\n{page_text}"
    return field_lines


def extract_web_certificate_fields(
    page_text: str,
    field_extractor: CertificateFieldExtractor,
) -> CccCertificateFields:
    return field_extractor.extract_from_web(page_text)


def format_cqc_page_plain_text(page_fields: dict[str, str]) -> str:
    """Render all CQC HTML page content as plain text."""
    visible_text = page_fields.get(VISIBLE_TEXT_KEY, "").strip()
    field_lines = [
        f"{label}: {value}"
        for label, value in page_fields.items()
        if label != VISIBLE_TEXT_KEY and value.strip()
    ]
    parts: list[str] = []
    if field_lines:
        parts.append("\n".join(field_lines))
    if visible_text:
        if parts:
            parts.append("")
        parts.append(visible_text)
    return "\n".join(parts)


def fetch_cqc_certificate_from_qr(
    qr_payloads: list[str],
    field_extractor: CertificateFieldExtractor | None,
) -> tuple[dict[str, str], CccCertificateFields | None, str | None, str | None]:
    """Fetch CQC HTML and return all page fields plus mapped certificate JSON."""
    url = select_cqc_url(qr_payloads)
    if url is None:
        return {}, None, None, None

    try:
        html = fetch_page_html(url)
        page_json = html_to_page_json(html)
        if len(page_json) <= 1 and len(page_json.get(VISIBLE_TEXT_KEY, "")) < MIN_PAGE_TEXT_LENGTH:
            raise CqcWebFetchError(
                "The CQC page did not contain enough readable certificate text."
            )

        certificate: CccCertificateFields | None = None
        if field_extractor is not None:
            page_text = page_content_for_extraction(html)
            certificate = extract_web_certificate_fields(page_text, field_extractor)

        return page_json, certificate, None, url
    except CqcWebFetchError as exc:
        return {}, None, str(exc), url
    except Exception as exc:  # noqa: BLE001
        return {}, None, f"{exc.__class__.__name__}: {exc}", url


def _collect_html_pairs(html: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for parser in (_HtmlTableExtractor(), _HtmlDefinitionListExtractor()):
        parser.feed(html)
        parser.close()
        pairs.extend(parser.pairs)
    return pairs


def _merge_field(field_map: dict[str, str], label: str, value: str) -> None:
    cleaned_label = re.sub(r"\s+", " ", label).strip()
    cleaned_value = re.sub(r"\s+", " ", value).strip()
    if not cleaned_label or not cleaned_value:
        return
    if cleaned_label in field_map and field_map[cleaned_label] != cleaned_value:
        field_map[cleaned_label] = f"{field_map[cleaned_label]}; {cleaned_value}"
        return
    field_map[cleaned_label] = cleaned_value


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


def _url_rank(url: str) -> int:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = {key.lower() for key in parse_qs(parsed.query)}
    if query.intersection(CERTIFICATE_QUERY_KEYS):
        return 0
    if any(token in path for token in ("certi", "query", "detail", "result")):
        return 1
    if parsed.netloc.lower().endswith("cqccms.com.cn"):
        return 2
    return 3
