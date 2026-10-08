from __future__ import annotations

import pytest

from app.errors import DocumentTypeError, VerificationSystemError
from app.services.ccc_verification import process_uploaded_document
from app.services.test_report_verification import verify_uploaded_test_report
from sandbox.app.verify_test_report.backend import ProductCategory, TestReportResult
from sandbox.src.errors import ExtractionError
from sandbox.src.schemas import CccCertificateFields, DocumentCategory, DocumentResult


class FakePipeline:
    def __init__(self, document: DocumentResult) -> None:
        self.document = document
        self.field_extractor = None

    def run(self, _path: object) -> DocumentResult:
        return self.document

    def extract_certificate_fields(self, _content: str) -> CccCertificateFields:
        return CccCertificateFields()


class FailingPipeline:
    def run(self, _path: object) -> DocumentResult:
        raise ExtractionError("Qwen extraction failed")

    def extract_certificate_fields(self, _content: str) -> CccCertificateFields:
        raise AssertionError("should not extract fields after run fails")


def test_ccc_rejects_non_certificate_category() -> None:
    document = DocumentResult(
        file_name="other.jpg",
        file_type="image",
        doc_category=DocumentCategory.OTHER,
        full_content="not a certificate",
    )
    with pytest.raises(DocumentTypeError, match="不是 CCC 证书"):
        process_uploaded_document(
            "other.jpg",
            b"not-empty",
            pipeline_factory=lambda: FakePipeline(document),
        )


def test_ccc_raises_system_error_on_pipeline_failure() -> None:
    with pytest.raises(VerificationSystemError, match="Qwen extraction failed"):
        process_uploaded_document(
            "cert.jpg",
            b"not-empty",
            pipeline_factory=FailingPipeline,
        )


def test_test_report_rejects_other_category() -> None:
    result = TestReportResult(
        file_name="report.pdf",
        page_count=1,
        product_category=ProductCategory.OTHER,
        category_reasoning="无法匹配已知产品类别。",
        full_content="unrelated text",
    )

    class FakeAnalyzer:
        def analyze(self, _path: object) -> TestReportResult:
            return result

    with pytest.raises(DocumentTypeError, match="不是可核验的检测报告"):
        verify_uploaded_test_report(
            "report.pdf",
            b"%PDF-1.4",
            analyzer_factory=FakeAnalyzer,
        )
