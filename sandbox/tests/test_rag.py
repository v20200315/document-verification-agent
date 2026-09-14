from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.documents import Document

from sandbox.app.simple_rag.backend import (
    RAGError,
    RAGIndex,
    RAGPage,
    SimplePDFRAG,
)
from sandbox.app.simple_rag.service import knowledge_source_signature
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


class VisionModel:
    def __init__(self, content: str = "Scanned page transcription.") -> None:
        self.content = content
        self.calls: list[Any] = []

    def invoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        return SimpleNamespace(content=self.content)


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
        vision_model=VisionModel(),
        embeddings=FakeEmbeddings(),
        answer_model=answer_model,
        max_attempts=1,
    )


def test_mixed_pdf_uses_text_layer_and_ocrs_only_scanned_pages() -> None:
    pages = [
        RAGPage(
            page_number=1,
            text="Digital page content.",
        ),
        RAGPage(
            page_number=2,
            image_data_url="data:image/png;base64,c2Nhbg==",
        ),
    ]
    vision_model = VisionModel()
    rag = SimplePDFRAG(
        loader=SimpleNamespace(load=lambda _path: pages),
        vision_model=vision_model,
        embeddings=FakeEmbeddings(),
        answer_model=StructuredAnswerModel([]),
        max_attempts=1,
    )

    index = rag.build_index("source.pdf")

    assert index.page_count == 2
    assert index.scanned_page_count == 1
    assert index.chunk_count == 2
    assert len(vision_model.calls) == 1
    image_blocks = vision_model.calls[0][1].content
    assert any(
        block.get("image_url", {}).get("url") == "data:image/png;base64,c2Nhbg=="
        for block in image_blocks
        if isinstance(block, dict)
    )


def test_answer_is_grounded_in_retrieved_page() -> None:
    documents = [
        Document(
            page_content="The warranty period is two years.",
            metadata={"page_number": 2, "source": "source.pdf"},
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
        source_name="source.pdf",
        page_count=2,
        scanned_page_count=0,
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
            metadata={"page_number": 1, "source": "source.pdf"},
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
        source_name="source.pdf",
        page_count=1,
        scanned_page_count=0,
        chunk_count=1,
    )

    answer = _rag(model).answer(index, "不存在的信息？")

    assert answer.has_sufficient_context is False
    assert answer.sources == []


def test_embedding_model_can_be_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("QWEN_EMBEDDING_MODEL", "custom-embedding")

    assert Settings.from_env().embedding_model == "custom-embedding"


def test_source_signature_changes_with_pdf_version(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1")
    first = knowledge_source_signature(pdf_path)
    pdf_path.write_bytes(b"%PDF-version-two")
    second = knowledge_source_signature(pdf_path)

    assert first != second


def test_missing_knowledge_pdf_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(RAGError, match="sandbox/knowledge/source.pdf"):
        knowledge_source_signature(tmp_path / "missing.pdf")
