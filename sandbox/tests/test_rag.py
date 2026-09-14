from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.documents import Document
from PIL import Image

from sandbox.app.simple_rag.backend import (
    RAGError,
    RAGIndex,
    RAGPage,
    SimplePDFRAG,
    TextPDFLoader,
)
from sandbox.app.simple_rag.service import load_uploaded_rag
from sandbox.src.config import Settings


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, float(index + 1)] for index, _text in enumerate(texts)]

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 1.0]


class StructuredAnswerModel:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[Any] = []

    def with_structured_output(self, _schema: Any, **_kwargs: Any) -> Any:
        return self

    def invoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        return self.responses.pop(0)


class FixedVectorStore:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.queries: list[tuple[str, int]] = []

    def similarity_search(self, query: str, k: int) -> list[Document]:
        self.queries.append((query, k))
        return self.documents


def _rag(answer_model: StructuredAnswerModel) -> SimplePDFRAG:
    return SimplePDFRAG(
        loader=SimpleNamespace(),
        embeddings=FakeEmbeddings(),
        answer_model=answer_model,
        max_attempts=1,
    )


def test_text_pdf_pages_are_indexed_without_ocr() -> None:
    pages = [
        RAGPage(page_number=1, text="First digital page."),
        RAGPage(page_number=2, text="Second digital page."),
    ]
    rag = SimplePDFRAG(
        loader=SimpleNamespace(load=lambda _path: pages),
        embeddings=FakeEmbeddings(),
        answer_model=StructuredAnswerModel([]),
        max_attempts=1,
    )

    index = rag.build_index("uploaded.pdf")

    assert index.page_count == 2
    assert index.chunk_count == 2
    assert index.source_name == "uploaded.pdf"


def test_image_only_pdf_is_rejected(tmp_path: Path) -> None:
    pdf_path = tmp_path / "image-only.pdf"
    Image.new("RGB", (40, 40), "white").save(pdf_path)

    with pytest.raises(RAGError, match="No selectable text"):
        TextPDFLoader().load(pdf_path)


def test_answer_is_grounded_in_retrieved_page() -> None:
    documents = [
        Document(
            page_content="The warranty period is two years.",
            metadata={"page_number": 2, "source": "uploaded.pdf"},
        )
    ]
    model = StructuredAnswerModel(
        [
            {
                "parsed": {
                    "answer": "保修期为两年。",
                    "has_sufficient_context": True,
                    "cited_pages": [2],
                },
                "parsing_error": None,
            }
        ]
    )
    vector_store = FixedVectorStore(documents)
    index = RAGIndex(
        vector_store=vector_store,
        source_name="uploaded.pdf",
        page_count=2,
        chunk_count=1,
    )

    answer = _rag(model).answer(index, "保修期是多久？")

    assert answer.answer == "保修期为两年。"
    assert answer.has_sufficient_context is True
    assert answer.sources[0].page_number == 2
    assert vector_store.queries == [("保修期是多久？", 4)]


def test_insufficient_context_returns_no_sources() -> None:
    documents = [
        Document(
            page_content="Unrelated content.",
            metadata={"page_number": 1, "source": "uploaded.pdf"},
        )
    ]
    model = StructuredAnswerModel(
        [
            {
                "parsed": {
                    "answer": "PDF 中没有足够信息回答该问题。",
                    "has_sufficient_context": False,
                    "cited_pages": [],
                },
                "parsing_error": None,
            }
        ]
    )
    index = RAGIndex(
        vector_store=FixedVectorStore(documents),
        source_name="uploaded.pdf",
        page_count=1,
        chunk_count=1,
    )

    answer = _rag(model).answer(index, "不存在的信息？")

    assert answer.has_sufficient_context is False
    assert answer.sources == []


def test_uploaded_pdf_is_removed_after_indexing() -> None:
    observed_paths: list[Path] = []
    fake_index = RAGIndex(
        vector_store=FixedVectorStore([]),
        source_name="knowledge.pdf",
        page_count=1,
        chunk_count=1,
    )

    class FakeRAG:
        def build_index(self, path: str | Path) -> RAGIndex:
            temporary_path = Path(path)
            observed_paths.append(temporary_path)
            assert temporary_path.is_file()
            return fake_index

    load_uploaded_rag.clear()
    with patch(
        "sandbox.app.simple_rag.service.SimplePDFRAG.from_env",
        return_value=FakeRAG(),
    ):
        _, index = load_uploaded_rag(
            "knowledge.pdf",
            b"%PDF-text",
            "test-fingerprint",
        )

    assert index is fake_index
    assert observed_paths
    assert all(not path.exists() for path in observed_paths)


def test_embedding_model_can_be_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("QWEN_EMBEDDING_MODEL", "custom-embedding")

    assert Settings.from_env().embedding_model == "custom-embedding"
