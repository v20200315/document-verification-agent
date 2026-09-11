from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from sandbox.app.pipeline_service import check_uploaded_information
from sandbox.src.errors import InfoCheckError
from sandbox.src.info_checker import (
    CNCAInfoChecker,
    extract_certificate_number,
)
from sandbox.src.schemas import (
    CertificateFieldName,
    DocumentCategory,
    DocumentResult,
    InfoCheckStatus,
    InfoComparisonReport,
)


class StructuredModel:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[Any] = []
        self.options: dict[str, Any] = {}

    def with_structured_output(self, _schema: Any, **kwargs: Any) -> Any:
        self.options = kwargs
        return self

    def invoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        return self.responses.pop(0)


def _comparison_items(
    mismatch_field: CertificateFieldName | None = None,
) -> list[dict[str, Any]]:
    items = []
    for field in CertificateFieldName:
        outcome = "Mismatch" if field is mismatch_field else "Match"
        items.append(
            {
                "field_name": field.value,
                "source_value": "证书值",
                "cnca_value": "数据库值",
                "outcome": outcome,
                "explanation": "字段一致。" if outcome == "Match" else "字段不一致。",
            }
        )
    return items


def _report_response(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "parsed": {
            "status": "All Matched",
            "comparisons": items,
            "summary": "已完成逐项比对。",
            "limitations": "模型生成的占位说明。",
            "evidence_image_count": 99,
        },
        "parsing_error": None,
    }


def _save_image(path: Path, color: str) -> None:
    Image.new("RGB", (20, 20), color).save(path)


def test_extracts_certificate_number_from_source_content() -> None:
    assert (
        extract_certificate_number(
            "中国国家强制性产品认证证书\n证书编号：2025010703748148"
        )
        == "2025010703748148"
    )
    assert extract_certificate_number("未提供证书编号") is None


def test_checker_extracts_multiple_images_then_compares(
    tmp_path: Path,
) -> None:
    first = tmp_path / "result-1.png"
    second = tmp_path / "result-2.jpg"
    _save_image(first, "white")
    _save_image(second, "gray")
    vision_model = StructuredModel(
        [
            {
                "parsed": {
                    "certificate_number": "2025010703748148",
                    "certificate_status": "有效",
                    "source_image_count": 2,
                },
                "parsing_error": None,
            }
        ]
    )
    text_model = StructuredModel(
        [_report_response(_comparison_items(CertificateFieldName.MANUFACTURER))]
    )

    report = CNCAInfoChecker(
        text_model=text_model,
        vision_model=vision_model,
        max_attempts=1,
    ).check("CCC 证书完整提取内容", [first, second])

    assert report.status is InfoCheckStatus.MISMATCH_FOUND
    assert report.evidence_image_count == 2
    assert "未直接连接国家认监委数据库" in report.limitations
    human_content = vision_model.calls[0][1].content
    assert sum(block["type"] == "image_url" for block in human_content) == 2
    assert vision_model.options["method"] == "json_schema"
    assert text_model.options["method"] == "json_schema"


def test_checker_rejects_comparison_missing_required_fields(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "result.png"
    _save_image(image_path, "white")
    vision_model = StructuredModel(
        [
            {
                "parsed": {
                    "certificate_number": "2025010703748148",
                    "source_image_count": 1,
                },
                "parsing_error": None,
            }
        ]
    )
    text_model = StructuredModel([_report_response(_comparison_items()[:-1])])

    checker = CNCAInfoChecker(text_model, vision_model, max_attempts=1)
    with pytest.raises(InfoCheckError, match="each certificate field"):
        checker.check("CCC certificate", [image_path])


def test_upload_service_removes_temporary_evidence() -> None:
    image = Image.new("RGB", (4, 4), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    observed_paths: list[Path] = []
    expected_report = InfoComparisonReport(
        status=InfoCheckStatus.ALL_MATCHED,
        comparisons=_comparison_items(),
        summary="全部一致。",
        limitations="仅供辅助核验。",
        evidence_image_count=1,
    )

    class FakeChecker:
        def check(
            self,
            _certificate_content: str,
            evidence_paths: list[Path],
        ) -> InfoComparisonReport:
            observed_paths.extend(evidence_paths)
            assert all(path.is_file() for path in evidence_paths)
            return expected_report

    document = DocumentResult(
        file_name="certificate.jpg",
        file_type="image",
        doc_category=DocumentCategory.CCC_CERTIFICATION,
        full_content="CCC certificate",
    )
    result = check_uploaded_information(
        document,
        [("cnca.png", buffer.getvalue())],
        checker_factory=FakeChecker,
    )

    assert result is expected_report
    assert observed_paths
    assert all(not path.exists() for path in observed_paths)
