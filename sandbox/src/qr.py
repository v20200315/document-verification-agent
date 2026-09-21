from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import zxingcpp
from PIL import Image, UnidentifiedImageError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
QR_RENDER_DPI = 180
CQC_HOST = "cqc.com.cn"


def decode_document_qr(file_path: str | Path) -> list[str]:
    """Decode QR payloads locally. Prefer CQC website URLs when several exist."""
    path = Path(file_path).expanduser().resolve()
    suffix = path.suffix.lower()
    try:
        if suffix in IMAGE_SUFFIXES:
            payloads = _decode_image_path(path)
        elif suffix == ".pdf":
            payloads = _decode_pdf_path(path)
        else:
            return []
    except Exception:  # noqa: BLE001
        return []
    return _order_payloads(payloads)


def _decode_image_path(path: Path) -> list[str]:
    try:
        with Image.open(path) as image:
            return _decode_pil_image(image.convert("RGB"))
    except (OSError, UnidentifiedImageError):
        return []


def _decode_pdf_path(path: Path) -> list[str]:
    payloads: list[str] = []
    document = None
    try:
        document = pdfium.PdfDocument(str(path))
        scale = QR_RENDER_DPI / 72
        for index in range(len(document)):
            page = document[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            try:
                payloads.extend(_decode_pil_image(image.convert("RGB")))
            finally:
                image.close()
                bitmap.close()
                page.close()
    except Exception:  # noqa: BLE001
        return []
    finally:
        if document is not None:
            document.close()
    return payloads


def _decode_pil_image(image: Image.Image) -> list[str]:
    results = zxingcpp.read_barcodes(image)
    payloads: list[str] = []
    for result in results:
        text = str(getattr(result, "text", "")).strip()
        if text:
            payloads.append(text)
    return payloads


def _order_payloads(payloads: list[str]) -> list[str]:
    ranked: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, payload in enumerate(payloads):
        if payload in seen:
            continue
        seen.add(payload)
        ranked.append((_payload_rank(payload), index, payload))
    ranked.sort()
    return [payload for _rank, _index, payload in ranked]


def _payload_rank(payload: str) -> int:
    lowered = payload.lower()
    if CQC_HOST in lowered and lowered.startswith(("http://", "https://")):
        return 0
    if lowered.startswith(("http://", "https://")):
        return 1
    return 2
