from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from app.errors import DocumentTypeError, VerificationSystemError
from sandbox.src.certificate_comparison import compare_certificate_sources
from sandbox.src.cqc_web import fetch_cqc_certificate_from_qr
from sandbox.src.errors import DocumentLoadError, DocumentPipelineError
from sandbox.src.pipeline import DocumentPipeline
from sandbox.src.qr import decode_document_qr
from sandbox.src.schemas import (
    CccCertificateFields,
    DocumentCategory,
    DocumentResult,
    ProcessedDocument,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_TEMP_ROOT = PROJECT_ROOT / "app" / "uploads" / ".tmp"
ALLOWED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}


class PipelineRunner(Protocol):
    def run(self, file_path: str | Path) -> DocumentResult: ...

    def extract_certificate_fields(self, full_content: str) -> CccCertificateFields: ...


def load_project_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def is_api_configured() -> bool:
    load_project_environment()
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())


def process_uploaded_document(
    file_name: str,
    data: bytes,
    pipeline_factory: Callable[[], PipelineRunner] = DocumentPipeline.from_env,
) -> ProcessedDocument:
    """Bridge byte uploads to extraction, QR decode, and MD5 without retaining files."""
    safe_name = _safe_file_name(file_name)
    if not data:
        raise DocumentLoadError("The uploaded file is empty.")

    file_md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    load_project_environment()
    UPLOAD_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="document-", dir=UPLOAD_TEMP_ROOT))
    temporary_path = temporary_dir / safe_name
    qr_payloads: list[str] = []
    field_extractor = None
    document: DocumentResult | None = None
    certificate: CccCertificateFields | None = None

    try:
        temporary_path.write_bytes(data)
        qr_payloads = decode_document_qr(temporary_path)
        try:
            pipeline = pipeline_factory()
            field_extractor = getattr(pipeline, "field_extractor", None)
            document = pipeline.run(temporary_path)
            certificate = pipeline.extract_certificate_fields(document.full_content)
        except DocumentPipelineError as exc:
            raise VerificationSystemError(str(exc)) from exc
        except Exception as exc:
            raise VerificationSystemError(f"{exc.__class__.__name__}: {exc}") from exc

        if (
            document is None
            or document.doc_category is not DocumentCategory.CCC_CERTIFICATION
        ):
            category = (
                document.doc_category.value if document is not None else "unknown"
            )
            raise DocumentTypeError(
                f"上传文件不是 CCC 证书，当前识别类型为：{category}。"
            )

        cqc_page_fields, cqc_certificate, cqc_fetch_error, cqc_source_url = (
            fetch_cqc_certificate_from_qr(qr_payloads, field_extractor)
        )
        cqc_comparison_report = compare_certificate_sources(
            image_certificate=certificate,
            website_certificate=cqc_certificate,
            website_source_url=cqc_source_url,
            website_fetch_error=cqc_fetch_error,
        )
        return ProcessedDocument(
            file_md5=file_md5,
            qr_payloads=qr_payloads,
            certificate=certificate,
            cqc_page_fields=cqc_page_fields,
            cqc_certificate=cqc_certificate,
            cqc_source_url=cqc_source_url,
            cqc_fetch_error=cqc_fetch_error,
            cqc_comparison_report=cqc_comparison_report,
            document=document,
        )
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _safe_file_name(file_name: str) -> str:
    base_name = Path(file_name).name
    suffix = Path(base_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        raise DocumentLoadError(
            f"Unsupported upload type {suffix!r}; expected: {allowed}"
        )

    sanitized_stem = re.sub(r"[^\w.-]+", "_", Path(base_name).stem).strip("._")[:100]
    return f"{sanitized_stem or 'upload'}{suffix}"
