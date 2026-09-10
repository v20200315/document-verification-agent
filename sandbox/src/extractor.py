from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from sandbox.src.errors import ExtractionError
from sandbox.src.llm import Invokable, invoke_with_retry, response_text
from sandbox.src.schemas import ExtractedPage, LoadedDocument, PageInput

SYSTEM_PROMPT = """You are a document transcription engine.
Extract the complete content of the supplied page without summarizing,
condensing, interpreting, translating, or omitting anything.
Preserve the original language, reading order, headings, labels, numbers,
dates, signatures, seals, and key-value relationships.
Represent tables faithfully as Markdown tables. Mark unreadable fragments as
[unreadable] rather than guessing. Return only the transcription."""


class ContentExtractor:
    """Extract page-by-page so one scanned page cannot hide later content."""

    def __init__(
        self,
        text_model: Invokable,
        vision_model: Invokable,
        max_attempts: int = 3,
    ) -> None:
        self.text_model = text_model
        self.vision_model = vision_model
        self.max_attempts = max_attempts

    def extract(self, document: LoadedDocument) -> list[ExtractedPage]:
        extracted: list[ExtractedPage] = []
        for page in document.pages:
            try:
                content = invoke_with_retry(
                    lambda page=page: self._extract_page(page),
                    self.max_attempts,
                )
            except Exception as exc:
                raise ExtractionError(
                    f"Extraction failed for page {page.page_number} of "
                    f"{document.file_name}: {exc}"
                ) from exc
            extracted.append(
                ExtractedPage(
                    page_number=page.page_number,
                    content=content,
                )
            )
        return extracted

    def _extract_page(self, page: PageInput) -> str:
        if page.route == "vision":
            if not page.image_data_url:
                raise ExtractionError(
                    f"Vision page {page.page_number} has no image data."
                )
            response = self.vision_model.invoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": (
                                    f"Transcribe page {page.page_number} exactly."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": page.image_data_url,
                                },
                            },
                        ]
                    ),
                ]
            )
        else:
            if not page.text:
                raise ExtractionError(
                    f"Text page {page.page_number} has no extracted text."
                )
            response = self.text_model.invoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=(
                            f"Transcribe page {page.page_number} faithfully "
                            "from this PDF text layer:\n\n"
                            f"{page.text}"
                        )
                    ),
                ]
            )
        return response_text(response)


def merge_pages(pages: list[ExtractedPage]) -> str:
    """Explicit boundaries preserve provenance after page-wise extraction."""
    return "\n\n".join(
        f"--- Page {page.page_number} ---\n{page.content}" for page in pages
    )
