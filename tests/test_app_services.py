from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from app.errors import DocumentTypeError, VerificationSystemError
from app.services.ccc_verification import process_uploaded_document
from app.services.test_report_verification import verify_uploaded_test_report
from sandbox.app.image_pdf_to_text.backend import ConversionResult
from sandbox.app.verify_test_report.backend import (
    IMAGE_ONLY_MESSAGE,
    ComplianceReport,
    ComplianceStatus,
    ProductCategory,
    RuleFinding,
    TestReportError,
    TestReportResult,
)
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


def _text_pdf_bytes() -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 720, "OCR extracted report text")
    canvas.save()
    return buffer.getvalue()


def test_test_report_ocrs_image_pdf_then_validates() -> None:
    classified = TestReportResult(
        file_name="ocr-report.pdf",
        page_count=1,
        product_category=ProductCategory.HEAT_FAN,
        category_reasoning="扫描件经 OCR 后可识别为热风机检测报告。",
        full_content="低环境温度空气源热泵热风机检测报告",
    )
    compliance = ComplianceReport(
        product_category=ProductCategory.HEAT_FAN,
        overall_status=ComplianceStatus.PASS,
        summary="全部规则通过。",
        findings=[
            RuleFinding(
                rule_number=1,
                rule_text="规则一",
                status=ComplianceStatus.PASS,
                evidence="报告中有对应描述。",
            )
        ],
    )
    analyzed_paths: list[str] = []

    class ImageThenTextAnalyzer:
        def analyze(self, pdf_path: object) -> TestReportResult:
            path = Path(pdf_path)
            analyzed_paths.append(path.name)
            if path.name.startswith("ocr-"):
                return classified
            raise TestReportError(IMAGE_ONLY_MESSAGE)

    class FakeConverter:
        def convert(self, _path: object) -> ConversionResult:
            pdf_data = _text_pdf_bytes()
            return ConversionResult(
                source_file_name="report.pdf",
                output_file_name="report_text.pdf",
                page_count=1,
                full_text="低环境温度空气源热泵热风机检测报告",
                pdf_data=pdf_data,
            )

    class FakeValidator:
        def validate(
            self,
            product_category: ProductCategory,
            full_content: str,
            rules_markdown: str,
        ) -> ComplianceReport:
            assert product_category is ProductCategory.HEAT_FAN
            assert "热风机" in full_content
            assert rules_markdown
            return compliance

    result, report, note = verify_uploaded_test_report(
        "report.pdf",
        b"%PDF-1.4 not-empty",
        analyzer_factory=ImageThenTextAnalyzer,
        converter_factory=FakeConverter,
        validator_factory=FakeValidator,
    )

    assert result == classified
    assert report == compliance
    assert note is None
    assert analyzed_paths[0] == "report.pdf"
    assert analyzed_paths[1].startswith("ocr-")


def test_test_report_skips_ocr_when_pdf_has_text() -> None:
    classified = TestReportResult(
        file_name="report.pdf",
        page_count=1,
        product_category=ProductCategory.GAS_BOILER,
        category_reasoning="文本 PDF 可直接分类。",
        full_content="燃气壁挂炉检测报告",
    )
    compliance = ComplianceReport(
        product_category=ProductCategory.GAS_BOILER,
        overall_status=ComplianceStatus.PASS,
        summary="全部规则通过。",
        findings=[
            RuleFinding(
                rule_number=1,
                rule_text="规则一",
                status=ComplianceStatus.PASS,
                evidence="报告中有对应描述。",
            )
        ],
    )
    converter_calls = 0

    class TextAnalyzer:
        def analyze(self, _path: object) -> TestReportResult:
            return classified

    class UnusedConverter:
        def convert(self, _path: object) -> ConversionResult:
            nonlocal converter_calls
            converter_calls += 1
            raise AssertionError("text PDFs should not run OCR")

    class FakeValidator:
        def validate(
            self,
            _product_category: ProductCategory,
            _full_content: str,
            _rules_markdown: str,
        ) -> ComplianceReport:
            return compliance

    verify_uploaded_test_report(
        "report.pdf",
        b"%PDF-1.4 not-empty",
        analyzer_factory=TextAnalyzer,
        converter_factory=UnusedConverter,
        validator_factory=FakeValidator,
    )
    assert converter_calls == 0
