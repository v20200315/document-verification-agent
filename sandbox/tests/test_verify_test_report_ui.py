from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from sandbox.app.verify_test_report.backend import (
    ComplianceReport,
    ComplianceStatus,
    ProductCategory,
    RuleFinding,
    TestReportResult,
)


def _classified_result(category: ProductCategory) -> TestReportResult:
    return TestReportResult(
        file_name="report.pdf",
        page_count=2,
        product_category=category,
        category_confidence=0.93,
        category_reasoning="铭牌标明燃气壁挂炉。"
        if category is ProductCategory.GAS_BOILER
        else "无法归入四类产品。",
        full_content="--- Page 1 ---\n燃气壁挂炉检测报告",
    )


def _compliance_report() -> ComplianceReport:
    return ComplianceReport(
        product_category=ProductCategory.GAS_BOILER,
        overall_status=ComplianceStatus.INSUFFICIENT,
        summary="报告证明了 CCC，但未提及保修年限。",
        findings=[
            RuleFinding(
                rule_number=1,
                rule_text="应具备 CCC 认证证书。",
                status=ComplianceStatus.PASS,
                evidence="报告写明具备 CCC 认证。",
            ),
            RuleFinding(
                rule_number=2,
                rule_text="应免费保修不低于 5 年。",
                status=ComplianceStatus.INSUFFICIENT,
                evidence="报告未提及保修承诺。",
            ),
        ],
    )


def test_classification_requires_explicit_click_and_supports_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    result = _classified_result(ProductCategory.GAS_BOILER)
    with patch(
        "sandbox.app.verify_test_report.service.classify_uploaded_pdf",
        return_value=result,
    ) as classify_mock:
        app_path = Path(__file__).parents[1] / "app" / "streamlit_app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.switch_page("app_pages/verify_test_report.py").run(timeout=10)

        assert not app.exception
        assert any(title.value == "Verify Test Report" for title in app.title)
        app.file_uploader[0].upload(
            "report.pdf",
            b"%PDF-text-report",
            "application/pdf",
        ).run(timeout=10)

        assert classify_mock.call_count == 0
        next(
            button for button in app.button if button.label.startswith("Classify")
        ).click().run(timeout=10)

        assert not app.exception
        assert classify_mock.call_count == 1
        assert app.text_area[0].value.endswith("燃气壁挂炉检测报告")
        assert any("铭牌标明燃气壁挂炉。" in str(item.value) for item in app.markdown)
        assert any(button.label.startswith("Validate") for button in app.button)

        next(
            button for button in app.button if button.label.startswith("New PDF")
        ).click().run(timeout=10)

        assert not app.exception
        assert app.file_uploader[0].value is None
        assert not app.text_area


def test_validate_button_is_hidden_for_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    with patch(
        "sandbox.app.verify_test_report.service.classify_uploaded_pdf",
        return_value=_classified_result(ProductCategory.OTHER),
    ):
        app_path = Path(__file__).parents[1] / "app" / "streamlit_app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.switch_page("app_pages/verify_test_report.py").run(timeout=10)
        app.file_uploader[0].upload(
            "report.pdf",
            b"%PDF-text-report",
            "application/pdf",
        ).run(timeout=10)
        next(
            button for button in app.button if button.label.startswith("Classify")
        ).click().run(timeout=10)

        assert not app.exception
        assert all(not button.label.startswith("Validate") for button in app.button)


def test_validation_requires_explicit_click_and_supports_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    with (
        patch(
            "sandbox.app.verify_test_report.service.classify_uploaded_pdf",
            return_value=_classified_result(ProductCategory.GAS_BOILER),
        ),
        patch(
            "sandbox.app.verify_test_report.service.validate_classified_report",
            return_value=_compliance_report(),
        ) as validate_mock,
    ):
        app_path = Path(__file__).parents[1] / "app" / "streamlit_app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.switch_page("app_pages/verify_test_report.py").run(timeout=10)
        app.file_uploader[0].upload(
            "report.pdf",
            b"%PDF-text-report",
            "application/pdf",
        ).run(timeout=10)
        next(
            button for button in app.button if button.label.startswith("Classify")
        ).click().run(timeout=10)

        assert validate_mock.call_count == 0
        next(
            button for button in app.button if button.label.startswith("Validate")
        ).click().run(timeout=10)

        assert not app.exception
        assert validate_mock.call_count == 1
        assert any(
            heading.value == "Compliance report / 核验报告" for heading in app.subheader
        )
        assert any(
            "报告证明了 CCC，但未提及保修年限。" in str(item.value)
            for item in app.markdown
        )

        next(
            button for button in app.button if button.label.startswith("New PDF")
        ).click().run(timeout=10)

        assert not app.exception
        assert all(not button.label.startswith("Validate") for button in app.button)
        assert all(
            heading.value != "Compliance report / 核验报告" for heading in app.subheader
        )
