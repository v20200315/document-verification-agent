from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
import zxingcpp
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from sandbox.app.pipeline_service import process_uploaded_document
from sandbox.src.certificate_fields import CertificateFieldExtractor
from sandbox.src.errors import DocumentLoadError, ExtractionError
from sandbox.src.qr import decode_document_qr
from sandbox.src.schemas import (
    CccCertificateFields,
    DocumentCategory,
    DocumentResult,
)

SAMPLE_CCC_TEXT = """生产企业名称及地址
浙江德富新能源技术有限公司
乐清市乐清湾港区乐商创业园创新路7号

产品名称和系列、型号、规格
低环境温度变频式空气源热泵（冷水）机组
DF-CTS064 I /04 220V～ 50Hz R410A

产品标准和技术要求
GB 17625.1–2022；GB 4343.1–2018；GB 4706.1–2005 ；GB 4706.32–2012

发证日期：2024 年 07 月 19 日    有效期至：2029 年 07 月 18 日
中国质量认证中心
CHINA QUALITY CERTIFICATION CENTRE
http://www.cqc.com.cn"""

CQC_URL = "https://www.cqc.com.cn/www/english/"


class SequenceModel:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[Any] = []

    def invoke(self, value: Any) -> Any:
        self.calls.append(value)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class StructuredFactory:
    def __init__(self, structured_model: SequenceModel) -> None:
        self.structured_model = structured_model
        self.options: dict[str, Any] = {}

    def with_structured_output(self, _schema: Any, **kwargs: Any) -> Any:
        self.options = kwargs
        return self.structured_model


class FakePipeline:
    def __init__(self, document: DocumentResult, fields: CccCertificateFields) -> None:
        self.document = document
        self.fields = fields

    def run(self, _path: Path) -> DocumentResult:
        return self.document

    def extract_certificate_fields(self, _content: str) -> CccCertificateFields:
        return self.fields


class FailingPipeline:
    def run(self, _path: Path) -> DocumentResult:
        raise ExtractionError("Qwen extraction failed")

    def extract_certificate_fields(self, _content: str) -> CccCertificateFields:
        raise AssertionError("fields should not be requested after extraction fails")


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _blank_png_bytes() -> bytes:
    return _png_bytes(Image.new("RGB", (80, 80), "white"))


def _qr_image(payload: str) -> Image.Image:
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    written = zxingcpp.write_barcode_to_image(barcode, scale=8)
    return Image.frombuffer(
        "L",
        (written.shape[1], written.shape[0]),
        bytes(written),
        "raw",
        "L",
        0,
        1,
    ).convert("RGB")


def _qr_png_bytes(payload: str) -> bytes:
    return _png_bytes(_qr_image(payload))


def test_certificate_extractor_parses_sample_structured_json() -> None:
    structured = SequenceModel(
        [
            {
                "parsed": {
                    "certificate_number": None,
                    "certificate_status": None,
                    "certificate_holder": None,
                    "manufacturer": (
                        "浙江德富新能源技术有限公司\n"
                        "乐清市乐清湾港区乐商创业园创新路7号"
                    ),
                    "production_factory": None,
                    "product_name": "低环境温度变频式空气源热泵（冷水）机组",
                    "models_and_specifications": "DF-CTS064 I /04 220V～ 50Hz R410A",
                    "applicable_standards": (
                        "GB 17625.1–2022；GB 4343.1–2018；"
                        "GB 4706.1–2005 ；GB 4706.32–2012"
                    ),
                    "issuing_certification_body": "中国质量认证中心",
                    "issue_date": "2024 年 07 月 19 日",
                    "valid_until": "2029 年 07 月 18 日",
                },
                "parsing_error": None,
            }
        ]
    )
    factory = StructuredFactory(structured)

    fields = CertificateFieldExtractor(factory, max_attempts=1).extract(SAMPLE_CCC_TEXT)

    assert fields.manufacturer is not None
    assert "浙江德富新能源技术有限公司" in fields.manufacturer
    assert fields.product_name == "低环境温度变频式空气源热泵（冷水）机组"
    assert fields.certificate_number is None
    assert factory.options["method"] == "json_schema"
    assert len(structured.calls) == 1


def test_certificate_extractor_returns_empty_fields_after_parse_failures() -> None:
    structured = SequenceModel(
        [
            {"parsed": None, "parsing_error": ValueError("bad JSON")},
            {"parsed": None, "parsing_error": ValueError("still bad")},
        ]
    )

    fields = CertificateFieldExtractor(
        StructuredFactory(structured), max_attempts=2
    ).extract(SAMPLE_CCC_TEXT)

    assert fields == CccCertificateFields()


def test_md5_uses_original_upload_bytes() -> None:
    data = _blank_png_bytes()
    expected = hashlib.md5(data, usedforsecurity=False).hexdigest()
    document = DocumentResult(
        file_name="upload.png",
        file_type="image",
        doc_category=DocumentCategory.CCC_CERTIFICATION,
        full_content="certificate text",
    )
    fields = CccCertificateFields(product_name="heat pump")

    processed = process_uploaded_document(
        "upload.png",
        data,
        pipeline_factory=lambda: FakePipeline(document, fields),
    )

    assert processed.file_md5 == expected
    assert processed.certificate == fields
    assert processed.document == document
    assert processed.processing_error is None


def test_qr_and_md5_remain_when_extraction_fails() -> None:
    data = _qr_png_bytes(CQC_URL)
    expected = hashlib.md5(data, usedforsecurity=False).hexdigest()

    processed = process_uploaded_document(
        "certificate.png",
        data,
        pipeline_factory=FailingPipeline,
    )

    assert processed.file_md5 == expected
    assert processed.qr_payloads[0] == CQC_URL
    assert processed.document is None
    assert processed.certificate is None
    assert processed.processing_error is not None
    assert "Qwen extraction failed" in processed.processing_error


def test_empty_upload_still_raises() -> None:
    with pytest.raises(DocumentLoadError, match="empty"):
        process_uploaded_document("upload.png", b"")


def test_decode_generated_qr_image(tmp_path: Path) -> None:
    image_path = tmp_path / "cqc.png"
    image_path.write_bytes(_qr_png_bytes(CQC_URL))

    assert decode_document_qr(image_path) == [CQC_URL]


def test_decode_prefers_cqc_url_over_other_payloads(tmp_path: Path) -> None:
    image_path = tmp_path / "mixed.png"
    other = _qr_image("https://example.com/other")
    cqc = _qr_image(CQC_URL)
    canvas_image = Image.new(
        "RGB",
        (other.width + cqc.width + 20, max(other.height, cqc.height)),
        "white",
    )
    canvas_image.paste(other, (0, 0))
    canvas_image.paste(cqc, (other.width + 20, 0))
    canvas_image.save(image_path)

    payloads = decode_document_qr(image_path)

    assert payloads[0] == CQC_URL
    assert "https://example.com/other" in payloads


def test_decode_no_qr_image(tmp_path: Path) -> None:
    image_path = tmp_path / "blank.png"
    image_path.write_bytes(_blank_png_bytes())

    assert decode_document_qr(image_path) == []


def test_decode_qr_in_pdf(tmp_path: Path) -> None:
    qr_path = tmp_path / "qr.png"
    qr_path.write_bytes(_qr_png_bytes(CQC_URL))
    pdf_path = tmp_path / "certificate.pdf"
    pdf = canvas.Canvas(str(pdf_path), pagesize=(300, 300))
    pdf.drawImage(ImageReader(str(qr_path)), 40, 40, width=220, height=220)
    pdf.save()

    assert CQC_URL in decode_document_qr(pdf_path)
