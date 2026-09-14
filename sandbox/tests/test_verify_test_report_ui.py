from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from sandbox.app.verify_test_report.backend import ProductCategory, TestReportResult


def test_classification_requires_explicit_click_and_supports_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    result = TestReportResult(
        file_name="report.pdf",
        page_count=2,
        product_category=ProductCategory.GAS_BOILER,
        category_confidence=0.93,
        category_reasoning="铭牌标明燃气壁挂炉。",
        full_content="--- Page 1 ---\n燃气壁挂炉检测报告",
    )
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

        next(
            button for button in app.button if button.label.startswith("New PDF")
        ).click().run(timeout=10)

        assert not app.exception
        assert app.file_uploader[0].value is None
        assert not app.text_area
