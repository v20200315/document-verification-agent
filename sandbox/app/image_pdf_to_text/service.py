from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from sandbox.app.image_pdf_to_text.backend import (
    ConversionResult,
    ImagePDFConversionError,
    ImagePDFConverter,
)

SANDBOX_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SANDBOX_DIR.parent
UPLOAD_TEMP_ROOT = SANDBOX_DIR / "uploads" / ".tmp"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class ConverterRunner(Protocol):
    def convert(self, pdf_path: str | Path) -> ConversionResult: ...


def is_api_configured() -> bool:
    """This application owns its environment setup and API readiness check."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())


def convert_uploaded_pdf(
    file_name: str,
    data: bytes,
    converter_factory: Callable[[], ConverterRunner] = ImagePDFConverter.from_env,
) -> ConversionResult:
    """Run path-based conversion without retaining the uploaded document."""
    safe_name = _safe_pdf_name(file_name)
    if not data:
        raise ImagePDFConversionError("The uploaded PDF is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImagePDFConversionError("The uploaded PDF exceeds the 50 MB limit.")

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    UPLOAD_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="image-pdf-", dir=UPLOAD_TEMP_ROOT))
    temporary_path = temporary_dir / safe_name
    try:
        temporary_path.write_bytes(data)
        return converter_factory().convert(temporary_path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _safe_pdf_name(file_name: str) -> str:
    base_name = Path(file_name).name
    if Path(base_name).suffix.lower() != ".pdf":
        raise ImagePDFConversionError("Only files with a .pdf extension are supported.")
    stem = re.sub(r"[^\w.-]+", "_", Path(base_name).stem).strip("._")[:100]
    return f"{stem or 'upload'}.pdf"
