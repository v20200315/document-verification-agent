from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from sandbox.src.classifier import DocumentClassifier
from sandbox.src.config import Settings
from sandbox.src.errors import ConfigurationError, DocumentLoadError
from sandbox.src.extractor import ContentExtractor, merge_pages
from sandbox.src.loaders import DocumentLoader
from sandbox.src.pipeline import DocumentPipeline
from sandbox.src.schemas import (
    ClassificationResult,
    DocumentCategory,
    ExtractedPage,
    LoadedDocument,
    PageInput,
)


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


def test_missing_api_key_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="DASHSCOPE_API_KEY"):
        Settings.from_env()


def test_image_load_routes_to_vision(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)

    loaded = DocumentLoader().load(image_path)

    assert loaded.file_type == "image"
    assert loaded.page_count is None
    assert loaded.pages[0].route == "vision"
    assert loaded.pages[0].image_data_url.startswith("data:image/jpeg;base64,")


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    text_path = tmp_path / "sample.txt"
    text_path.write_text("not a document")
    with pytest.raises(DocumentLoadError, match="Unsupported"):
        DocumentLoader().load(text_path)


def test_mixed_pdf_routes_each_page_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "mixed.pdf"
    pdf_path.write_bytes(b"%PDF-placeholder")

    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        is_encrypted = False

        def __init__(self, _path: str) -> None:
            self.pages = [
                FakePage("A digital page with enough meaningful text."),
                FakePage(""),
            ]

    monkeypatch.setattr("sandbox.src.loaders.PdfReader", FakeReader)
    monkeypatch.setattr(
        DocumentLoader,
        "_render_pdf_pages",
        lambda _self, _path, indices: {
            index: "data:image/png;base64,c2Nhbg==" for index in indices
        },
    )

    loaded = DocumentLoader(scanned_text_threshold=20).load(pdf_path)

    assert loaded.page_count == 2
    assert [page.route for page in loaded.pages] == ["text", "vision"]
    assert loaded.pages[1].image_data_url == ("data:image/png;base64,c2Nhbg==")


def test_extractor_retries_empty_response_and_preserves_page_order() -> None:
    text_model = SequenceModel(
        [SimpleNamespace(content=""), SimpleNamespace(content="digital text")]
    )
    vision_model = SequenceModel([SimpleNamespace(content="scanned text")])
    document = LoadedDocument(
        file_name="mixed.pdf",
        file_type="pdf",
        page_count=2,
        pages=[
            PageInput(page_number=1, route="text", text="raw text"),
            PageInput(
                page_number=2,
                route="vision",
                image_data_url="data:image/png;base64,c2Nhbg==",
            ),
        ],
    )

    pages = ContentExtractor(
        text_model=text_model,
        vision_model=vision_model,
        max_attempts=2,
    ).extract(document)

    assert len(text_model.calls) == 2
    assert merge_pages(pages) == (
        "--- Page 1 ---\ndigital text\n\n--- Page 2 ---\nscanned text"
    )


def test_classifier_retries_malformed_structured_output() -> None:
    structured = SequenceModel(
        [
            {"parsed": None, "parsing_error": ValueError("bad JSON")},
            {
                "parsed": {
                    "doc_category": "Authorization Document",
                    "category_confidence": 0.95,
                    "category_reasoning": "The title states authorization.",
                },
                "parsing_error": None,
            },
        ]
    )
    factory = StructuredFactory(structured)

    result = DocumentClassifier(factory, max_attempts=2).classify("授权证书")

    assert result.doc_category is DocumentCategory.AUTHORIZATION
    assert result.category_confidence == 0.95
    assert len(structured.calls) == 2
    assert factory.options["method"] == "json_schema"


def test_classifier_gracefully_falls_back_after_parse_failures() -> None:
    structured = SequenceModel(
        [
            {"parsed": None, "parsing_error": ValueError("bad JSON")},
            {"parsed": None, "parsing_error": ValueError("still bad")},
        ]
    )
    result = DocumentClassifier(StructuredFactory(structured), max_attempts=2).classify(
        "unknown"
    )

    assert result.doc_category is DocumentCategory.OTHER
    assert result.category_confidence is None
    assert "unavailable after retries" in (result.category_reasoning or "")


def test_pipeline_assembles_expected_json_shape() -> None:
    loaded = LoadedDocument(
        file_name="temp01.jpg",
        file_type="image",
        pages=[
            PageInput(
                page_number=1,
                route="vision",
                image_data_url="data:image/jpeg;base64,aW1hZ2U=",
            )
        ],
    )

    loader = SimpleNamespace(load=lambda _path: loaded)
    extractor = SimpleNamespace(
        extract=lambda _document: [ExtractedPage(page_number=1, content="授权证书")]
    )
    classifier = SimpleNamespace(
        classify=lambda _content: ClassificationResult(
            doc_category=DocumentCategory.AUTHORIZATION,
            category_confidence=0.99,
            category_reasoning="Authorization wording is explicit.",
        )
    )

    result = DocumentPipeline(loader, extractor, classifier).run("temp01.jpg")
    payload = result.model_dump(mode="json", exclude_none=True)

    assert payload == {
        "file_name": "temp01.jpg",
        "file_type": "image",
        "doc_category": "Authorization Document",
        "category_confidence": 0.99,
        "category_reasoning": "Authorization wording is explicit.",
        "full_content": "--- Page 1 ---\n授权证书",
    }
