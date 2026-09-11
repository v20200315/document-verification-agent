from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from sandbox.src.schemas import (
    PageTamperingAssessment,
    TamperingRisk,
    TamperingStatus,
)
from sandbox.src.tampering import LIMITATIONS, SYSTEM_PROMPT, TamperingAnalyzer


class StructuredVisionModel:
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


def _assessment(
    page_number: int,
    risk: str,
    suspected: bool | None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "parsed": {
            "page_number": page_number,
            "risk_level": risk,
            "suspected_tampering": suspected,
            "findings": findings or [],
            "summary": f"Page {page_number} assessment.",
        },
        "parsing_error": None,
    }


def test_image_tampering_analysis_returns_independent_checkpoint(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "certificate.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    model = StructuredVisionModel([_assessment(1, "Low", False)])

    report = TamperingAnalyzer(model, max_attempts=1).analyze(image_path)

    assert report.check_type == "Visual Tampering Analysis"
    assert report.status is TamperingStatus.NO_OBVIOUS_INDICATORS
    assert report.risk_level is TamperingRisk.LOW
    assert report.suspected_tampering is False
    assert report.pages_analyzed == 1
    assert "不能作为文件真实性证明" in report.limitations
    assert "简体中文" in SYSTEM_PROMPT
    assert report.limitations == LIMITATIONS
    assert model.options["method"] == "json_schema"


def test_multi_page_analysis_uses_highest_risk_and_merges_findings(
    monkeypatch,
) -> None:
    model = StructuredVisionModel(
        [
            _assessment(1, "Low", False),
            _assessment(
                2,
                "High",
                True,
                [
                    {
                        "page_number": 99,
                        "location": "Certificate number",
                        "observation": "Visible font and edge mismatch.",
                        "severity": "High",
                    }
                ],
            ),
        ]
    )
    analyzer = TamperingAnalyzer(model, max_attempts=1)
    monkeypatch.setattr(
        analyzer,
        "_load_visual_pages",
        lambda _path: [
            (1, "data:image/png;base64,cGFnZTE="),
            (2, "data:image/png;base64,cGFnZTI="),
        ],
    )

    report = analyzer.analyze("placeholder.pdf")

    assert report.status is TamperingStatus.REVIEW_REQUIRED
    assert report.risk_level is TamperingRisk.HIGH
    assert report.suspected_tampering is True
    assert report.pages_analyzed == 2
    assert len(report.findings) == 1
    assert report.findings[0].page_number == 2


def test_page_assessment_schema_rejects_unknown_risk() -> None:
    try:
        PageTamperingAssessment.model_validate(
            {
                "page_number": 1,
                "risk_level": "Certain",
                "summary": "Invalid risk.",
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown tampering risk must be rejected.")
