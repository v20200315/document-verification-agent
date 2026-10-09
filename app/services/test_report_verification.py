from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from app.errors import DocumentTypeError, VerificationSystemError
from sandbox.app.image_pdf_to_text.backend import (
    ConversionResult,
    ImagePDFConversionError,
    ImagePDFConverter,
)
from sandbox.app.verify_test_report.backend import (
    IMAGE_ONLY_MESSAGE,
    ComplianceReport,
    ProductCategory,
    TestReportAnalyzer,
    TestReportError,
    TestReportResult,
    TestReportValidator,
    load_category_rules,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_TEMP_ROOT = PROJECT_ROOT / "app" / "uploads" / ".tmp"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class AnalyzerRunner(Protocol):
    def analyze(self, pdf_path: str | Path) -> TestReportResult: ...


class ValidatorRunner(Protocol):
    def validate(
        self,
        product_category: ProductCategory,
        full_content: str,
        rules_markdown: str,
    ) -> ComplianceReport: ...


class ConverterRunner(Protocol):
    def convert(self, pdf_path: str | Path) -> ConversionResult: ...


def is_api_configured() -> bool:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())


def classify_uploaded_pdf(
    file_name: str,
    data: bytes,
    analyzer_factory: Callable[[], AnalyzerRunner] = TestReportAnalyzer.from_env,
    converter_factory: Callable[[], ConverterRunner] = ImagePDFConverter.from_env,
) -> TestReportResult:
    safe_name = _safe_pdf_name(file_name)
    if not data:
        raise TestReportError("The uploaded PDF is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise TestReportError("The uploaded PDF exceeds the 50 MB limit.")

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    UPLOAD_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="test-report-", dir=UPLOAD_TEMP_ROOT))
    temporary_path = temporary_dir / safe_name
    try:
        temporary_path.write_bytes(data)
        analyzer = analyzer_factory()
        try:
            return analyzer.analyze(temporary_path)
        except TestReportError as exc:
            if not _is_image_only_pdf(exc):
                raise
            try:
                conversion = converter_factory().convert(temporary_path)
            except ImagePDFConversionError as ocr_exc:
                raise VerificationSystemError(
                    f"图片型 PDF OCR 失败：{ocr_exc}"
                ) from ocr_exc
            ocr_path = temporary_dir / f"ocr-{safe_name}"
            ocr_path.write_bytes(conversion.pdf_data)
            return analyzer.analyze(ocr_path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def validate_classified_report(
    result: TestReportResult,
    validator_factory: Callable[[], ValidatorRunner] = TestReportValidator.from_env,
    rules_dir: str | Path | None = None,
) -> ComplianceReport:
    if result.product_category is ProductCategory.OTHER:
        raise TestReportError(
            "Validation is only available after a product category "
            "other than Other has been classified."
        )

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    rules = load_category_rules(rules_dir)
    return validator_factory().validate(
        result.product_category,
        result.full_content,
        rules[result.product_category],
    )


def verify_uploaded_test_report(
    file_name: str,
    data: bytes,
    analyzer_factory: Callable[[], AnalyzerRunner] = TestReportAnalyzer.from_env,
    validator_factory: Callable[[], ValidatorRunner] = TestReportValidator.from_env,
    converter_factory: Callable[[], ConverterRunner] = ImagePDFConverter.from_env,
    rules_dir: str | Path | None = None,
) -> tuple[TestReportResult, ComplianceReport | None, str | None]:
    """Classify a PDF (OCR image PDFs first) and validate when the category supports it."""
    classification = classify_uploaded_pdf(
        file_name,
        data,
        analyzer_factory=analyzer_factory,
        converter_factory=converter_factory,
    )
    if classification.product_category is ProductCategory.OTHER:
        raise DocumentTypeError(
            "上传文件不是可核验的检测报告（产品类别为 Other）。"
        )
    report = validate_classified_report(
        classification,
        validator_factory=validator_factory,
        rules_dir=rules_dir,
    )
    return classification, report, None


def _is_image_only_pdf(exc: TestReportError) -> bool:
    message = str(exc)
    return message == IMAGE_ONLY_MESSAGE or "No selectable text was found" in message


def _safe_pdf_name(file_name: str) -> str:
    base_name = Path(file_name).name
    if Path(base_name).suffix.lower() != ".pdf":
        raise TestReportError("Only files with a .pdf extension are supported.")
    stem = re.sub(r"[^\w.-]+", "_", Path(base_name).stem).strip("._")[:100]
    return f"{stem or 'upload'}.pdf"
