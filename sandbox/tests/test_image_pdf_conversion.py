from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image
from pypdf import PdfReader

from sandbox.app.image_pdf_to_text.backend import (
    ConversionResult,
    ImagePDFConversionError,
    ImagePDFConverter,
    PDFPageRenderer,
    RenderedPage,
    build_text_pdf,
)
from sandbox.app.image_pdf_to_text.service import convert_uploaded_pdf


class FakeRenderer:
    def __init__(self, pages: list[RenderedPage]) -> None:
        self.pages = pages
        self.paths: list[Path] = []

    def render(self, path: str | Path):
        self.paths.append(Path(path))
        yield from self.pages


class SequenceVisionModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[Any] = []

    def invoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        return SimpleNamespace(content=self.responses.pop(0))


def test_converter_processes_every_page_and_builds_searchable_pdf() -> None:
    renderer = FakeRenderer(
        [
            RenderedPage(1, "data:image/png;base64,cGFnZTE="),
            RenderedPage(2, "data:image/png;base64,cGFnZTI="),
        ]
    )
    vision_model = SequenceVisionModel(["第一页中文内容", "Second page text"])
    converter = ImagePDFConverter(
        renderer=renderer,
        vision_model=vision_model,
        max_attempts=1,
    )

    result = converter.convert("scanned.pdf")

    assert result.page_count == 2
    assert result.output_file_name == "scanned_text.pdf"
    assert "第一页中文内容" in result.full_text
    assert len(vision_model.calls) == 2
    output_reader = PdfReader(BytesIO(result.pdf_data))
    extracted = "\n".join(page.extract_text() or "" for page in output_reader.pages)
    assert "第一页中文内容" in extracted
    assert "Second page text" in extracted


def test_renderer_renders_all_image_pdf_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "images.pdf"
    first = Image.new("RGB", (20, 20), "white")
    second = Image.new("RGB", (20, 20), "black")
    first.save(pdf_path, save_all=True, append_images=[second])

    pages = list(PDFPageRenderer(render_dpi=72).render(pdf_path))

    assert [page.page_number for page in pages] == [1, 2]
    assert all(
        page.image_data_url.startswith("data:image/png;base64,") for page in pages
    )


def test_empty_ocr_response_is_retried() -> None:
    renderer = FakeRenderer([RenderedPage(1, "data:image/png;base64,cGFnZQ==")])
    vision_model = SequenceVisionModel(["", "Recovered text"])

    result = ImagePDFConverter(
        renderer,
        vision_model,
        max_attempts=2,
    ).convert("scan.pdf")

    assert result.full_text.endswith("Recovered text")
    assert len(vision_model.calls) == 2


def test_build_text_pdf_requires_pages() -> None:
    with pytest.raises(ImagePDFConversionError, match="At least one"):
        build_text_pdf([], title="empty")


def test_upload_service_removes_temporary_pdf() -> None:
    observed_paths: list[Path] = []
    expected = ConversionResult(
        source_file_name="source.pdf",
        output_file_name="source_text.pdf",
        page_count=1,
        full_text="OCR text",
        pdf_data=b"%PDF-test",
    )

    class FakeConverter:
        def convert(self, path: str | Path) -> ConversionResult:
            temporary_path = Path(path)
            observed_paths.append(temporary_path)
            assert temporary_path.is_file()
            return expected

    result = convert_uploaded_pdf(
        "source.pdf",
        b"%PDF-upload",
        converter_factory=FakeConverter,
    )

    assert result is expected
    assert observed_paths
    assert all(not path.exists() for path in observed_paths)
