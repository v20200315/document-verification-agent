from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from sandbox.src.schemas import RAGAnswer, RAGSource


class FakeRAG:
    def answer(self, _index, question: str) -> RAGAnswer:
        assert question == "证书有效期多久？"
        return RAGAnswer(
            answer="证书有效期为五年。",
            has_sufficient_context=True,
            sources=[
                RAGSource(
                    page_number=3,
                    excerpt="本证书有效期为五年。",
                )
            ],
        )


def test_simple_rag_page_initializes_and_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    index = SimpleNamespace(
        page_count=5,
        scanned_page_count=2,
        chunk_count=12,
    )
    with (
        patch(
            "sandbox.app.rag_service.knowledge_source_signature",
            return_value=("/tmp/source.pdf", 123, 456),
        ),
        patch(
            "sandbox.app.rag_service.load_cached_rag",
            return_value=(FakeRAG(), index),
        ) as load_mock,
    ):
        app_path = Path(__file__).parents[1] / "app" / "streamlit_app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.switch_page("app_pages/simple_rag.py").run(timeout=10)

        assert not app.exception
        assert any(title.value == "Simple RAG / PDF 问答" for title in app.title)
        next(
            button
            for button in app.button
            if button.label.startswith("Initialize knowledge base")
        ).click().run(timeout=10)

        assert load_mock.call_count == 1
        assert [metric.value for metric in app.metric] == ["5", "2", "12"]
        app.chat_input[0].set_value("证书有效期多久？").run(timeout=10)

        assert not app.exception
        assert any(markdown.value == "证书有效期为五年。" for markdown in app.markdown)
