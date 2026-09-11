from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from sandbox.src.errors import DocumentLoadError
from sandbox.src.info_checker import MAX_EVIDENCE_IMAGES, CNCAInfoChecker
from sandbox.src.pipeline import DocumentPipeline
from sandbox.src.schemas import (
    DocumentResult,
    InfoComparisonReport,
    TamperingReport,
)
from sandbox.src.tampering import TamperingAnalyzer

SANDBOX_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SANDBOX_DIR.parent
UPLOAD_TEMP_ROOT = SANDBOX_DIR / "uploads" / ".tmp"
ALLOWED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}
EVIDENCE_SUFFIXES = {".jpg", ".jpeg", ".png"}
MAX_EVIDENCE_IMAGE_BYTES = 10 * 1024 * 1024


class PipelineRunner(Protocol):
    def run(self, file_path: str | Path) -> DocumentResult: ...


class InfoCheckerRunner(Protocol):
    def check(
        self,
        certificate_content: str,
        evidence_paths: list[Path],
    ) -> InfoComparisonReport: ...


def load_project_environment() -> None:
    """Fill missing process values from .env without overriding shell config."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def is_api_configured() -> bool:
    load_project_environment()
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())


def process_uploaded_document(
    file_name: str,
    data: bytes,
    pipeline_factory: Callable[[], PipelineRunner] = DocumentPipeline.from_env,
) -> DocumentResult:
    """Bridge byte uploads to the path-based pipeline without retaining files."""
    safe_name = _safe_file_name(file_name)
    if not data:
        raise DocumentLoadError("The uploaded file is empty.")

    load_project_environment()
    UPLOAD_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="document-", dir=UPLOAD_TEMP_ROOT))
    temporary_path = temporary_dir / safe_name

    try:
        temporary_path.write_bytes(data)
        return pipeline_factory().run(temporary_path)
    finally:
        # Failed LLM calls must not leave user documents on the server.
        shutil.rmtree(temporary_dir, ignore_errors=True)


def analyze_uploaded_document(
    file_name: str,
    data: bytes,
    analyzer_factory: Callable[[], TamperingAnalyzer] = (TamperingAnalyzer.from_env),
) -> TamperingReport:
    """Run the independent visual checkpoint against the original file bytes."""
    safe_name = _safe_file_name(file_name)
    if not data:
        raise DocumentLoadError("The uploaded file is empty.")

    load_project_environment()
    UPLOAD_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="tampering-", dir=UPLOAD_TEMP_ROOT))
    temporary_path = temporary_dir / safe_name

    try:
        temporary_path.write_bytes(data)
        return analyzer_factory().analyze(temporary_path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def check_uploaded_information(
    document_result: DocumentResult,
    evidence_uploads: list[tuple[str, bytes]],
    checker_factory: Callable[[], InfoCheckerRunner] = CNCAInfoChecker.from_env,
) -> InfoComparisonReport:
    """Bridge multiple screenshot uploads to the path-based evidence checker."""
    if not 1 <= len(evidence_uploads) <= MAX_EVIDENCE_IMAGES:
        raise DocumentLoadError(
            f"Upload between 1 and {MAX_EVIDENCE_IMAGES} CNCA screenshots."
        )

    load_project_environment()
    UPLOAD_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="cnca-info-", dir=UPLOAD_TEMP_ROOT))
    evidence_paths: list[Path] = []

    try:
        for index, (file_name, data) in enumerate(evidence_uploads, start=1):
            safe_name = _safe_evidence_name(file_name)
            if not data:
                raise DocumentLoadError(f"Evidence image {file_name!r} is empty.")
            if len(data) > MAX_EVIDENCE_IMAGE_BYTES:
                raise DocumentLoadError(
                    f"Evidence image {file_name!r} exceeds the 10 MB limit."
                )
            path = temporary_dir / f"{index:02d}-{safe_name}"
            path.write_bytes(data)
            evidence_paths.append(path)

        return checker_factory().check(
            document_result.full_content,
            evidence_paths,
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


def _safe_evidence_name(file_name: str) -> str:
    base_name = Path(file_name).name
    suffix = Path(base_name).suffix.lower()
    if suffix not in EVIDENCE_SUFFIXES:
        raise DocumentLoadError(
            f"Unsupported evidence type {suffix!r}; expected JPG or PNG."
        )
    sanitized_stem = re.sub(r"[^\w.-]+", "_", Path(base_name).stem).strip("._")[:100]
    return f"{sanitized_stem or 'evidence'}{suffix}"
