from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from sandbox.app.image_pdf_to_text.backend import ConversionResult


def test_conversion_requires_explicit_click_and_supports_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    result = ConversionResult(
        source_file_name="scan.pdf",
        output_file_name="scan_text.pdf",
        page_count=2,
        full_text="--- Source Page 1 ---\n第一页",
        pdf_data=b"%PDF-generated",
    )
    with patch(
        "sandbox.app.image_pdf_to_text.service.convert_uploaded_pdf",
        return_value=result,
    ) as convert_mock:
        app_path = Path(__file__).parents[1] / "app" / "streamlit_app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.switch_page("app_pages/image_pdf_to_text.py").run(timeout=10)

        assert not app.exception
        assert any(title.value == "Image PDF to Text PDF" for title in app.title)
        app.file_uploader[0].upload(
            "scan.pdf",
            b"%PDF-image-pages",
            "application/pdf",
        ).run(timeout=10)

        assert convert_mock.call_count == 0
        next(
            button for button in app.button if button.label.startswith("Convert")
        ).click().run(timeout=10)

        assert not app.exception
        assert convert_mock.call_count == 1
        assert app.text_area[0].value.endswith("第一页")
        assert app.download_button

        next(
            button for button in app.button if button.label.startswith("New PDF")
        ).click().run(timeout=10)

        assert not app.exception
        assert app.file_uploader[0].value is None
        assert not app.download_button
