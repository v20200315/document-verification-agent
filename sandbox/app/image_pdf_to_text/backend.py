from __future__ import annotations

import base64
import io
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import pypdfium2 as pdfium
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from pypdf import PdfReader
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from sandbox.src.config import Settings
from sandbox.src.llm import (
    Invokable,
    build_models,
    invoke_with_retry,
    response_text,
)

OCR_PROMPT = """You are a precise OCR transcription engine.
Transcribe every visible text element from the supplied PDF page without
summarizing, translating, interpreting, or omitting content. Preserve reading
order, headings, labels, numbers, dates, table relationships, and original
language. Represent tables as readable Markdown-style rows. Mark unreadable
fragments as [unreadable] instead of guessing. Return only the transcription."""

OUTPUT_FONT = "STSong-Light"


class ImagePDFConversionError(RuntimeError):
    """Error boundary owned by this independent conversion application."""


class OCRPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str = Field(min_length=1)


class ConversionResult(BaseModel):
    source_file_name: str = Field(min_length=1)
    output_file_name: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    full_text: str = Field(min_length=1)
    pdf_data: bytes = Field(min_length=1)


@dataclass(slots=True)
class RenderedPage:
    page_number: int
    image_data_url: str


class PDFPageRenderer:
    """Validate the source and stream rendered pages to limit peak memory."""

    def __init__(self, render_dpi: int = 180) -> None:
        self.render_dpi = render_dpi

    def render(self, pdf_path: str | Path) -> Iterator[RenderedPage]:
        path = Path(pdf_path).expanduser().resolve()
        page_count = self._validate(path)
        document = None
        try:
            document = pdfium.PdfDocument(str(path))
            scale = self.render_dpi / 72
            for index in range(page_count):
                page = bitmap = image = None
                try:
                    page = document[index]
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil()
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    yield RenderedPage(
                        page_number=index + 1,
                        image_data_url=_data_url(
                            buffer.getvalue(),
                            "image/png",
                        ),
                    )
                finally:
                    if image is not None:
                        image.close()
                    if bitmap is not None:
                        bitmap.close()
                    if page is not None:
                        page.close()
        except ImagePDFConversionError:
            raise
        except Exception as exc:
            raise ImagePDFConversionError(
                f"Unable to render {path.name}: {exc}"
            ) from exc
        finally:
            if document is not None:
                document.close()

    @staticmethod
    def _validate(path: Path) -> int:
        if not path.is_file():
            raise ImagePDFConversionError(f"Input PDF does not exist: {path}")
        if path.suffix.lower() != ".pdf":
            raise ImagePDFConversionError("Only PDF uploads can be converted.")
        if path.stat().st_size == 0:
            raise ImagePDFConversionError("The uploaded PDF is empty.")
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise ImagePDFConversionError(f"PDF {path.name} is password-protected.")
            page_count = len(reader.pages)
        except ImagePDFConversionError:
            raise
        except Exception as exc:
            raise ImagePDFConversionError(f"Unable to read {path.name}: {exc}") from exc
        if page_count == 0:
            raise ImagePDFConversionError(f"PDF {path.name} contains no pages.")
        return page_count


class ImagePDFConverter:
    """Render every page, transcribe with Qwen-VL, then rebuild searchable PDF."""

    def __init__(
        self,
        renderer: PDFPageRenderer,
        vision_model: Invokable,
        max_attempts: int = 3,
    ) -> None:
        self.renderer = renderer
        self.vision_model = vision_model
        self.max_attempts = max_attempts

    @classmethod
    def from_settings(cls, settings: Settings) -> ImagePDFConverter:
        _, vision_model = build_models(settings)
        return cls(
            renderer=PDFPageRenderer(render_dpi=settings.pdf_render_dpi),
            vision_model=vision_model,
            max_attempts=settings.max_retries,
        )

    @classmethod
    def from_env(cls) -> ImagePDFConverter:
        return cls.from_settings(Settings.from_env())

    def convert(self, pdf_path: str | Path) -> ConversionResult:
        path = Path(pdf_path).expanduser().resolve()
        pages: list[OCRPage] = []
        for rendered_page in self.renderer.render(path):
            try:
                text = invoke_with_retry(
                    lambda page=rendered_page: self._transcribe_page(page),
                    self.max_attempts,
                )
            except Exception as exc:
                raise ImagePDFConversionError(
                    f"OCR failed for page {rendered_page.page_number} "
                    f"of {path.name}: {exc}"
                ) from exc
            pages.append(
                OCRPage(
                    page_number=rendered_page.page_number,
                    text=text,
                )
            )

        if not pages:
            raise ImagePDFConversionError(f"No pages were rendered from {path.name}.")
        try:
            pdf_data = build_text_pdf(pages, title=path.stem)
        except Exception as exc:
            raise ImagePDFConversionError(
                f"Unable to generate the text PDF: {exc}"
            ) from exc

        full_text = "\n\n".join(
            f"--- Source Page {page.page_number} ---\n{page.text}" for page in pages
        )
        return ConversionResult(
            source_file_name=path.name,
            output_file_name=f"{path.stem}_text.pdf",
            page_count=len(pages),
            full_text=full_text,
            pdf_data=pdf_data,
        )

    def _transcribe_page(self, page: RenderedPage) -> str:
        response = self.vision_model.invoke(
            [
                SystemMessage(content=OCR_PROMPT),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": (
                                f"Transcribe source page {page.page_number} exactly."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": page.image_data_url},
                        },
                    ]
                ),
            ]
        )
        return response_text(response)


def build_text_pdf(pages: list[OCRPage], title: str) -> bytes:
    """Build a reflowed Unicode PDF while retaining source-page boundaries."""
    if not pages:
        raise ImagePDFConversionError(
            "At least one OCR page is required to build a PDF."
        )
    if OUTPUT_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(OUTPUT_FONT))

    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        title=title,
        author="Document Verification Agent",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    heading_style = ParagraphStyle(
        "SourcePageHeading",
        fontName=OUTPUT_FONT,
        fontSize=13,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "OCRBody",
        fontName=OUTPUT_FONT,
        fontSize=10,
        leading=15,
        wordWrap="CJK",
        splitLongWords=True,
    )

    story = []
    for index, page in enumerate(pages):
        if index:
            story.append(PageBreak())
        story.append(
            Paragraph(
                f"原始文件第 {page.page_number} 页",
                heading_style,
            )
        )
        story.append(Spacer(1, 3 * mm))
        paragraphs = page.text.split("\n\n")
        for paragraph in paragraphs:
            safe_text = escape(paragraph).replace("\n", "<br/>")
            story.append(Paragraph(safe_text or " ", body_style))
            story.append(Spacer(1, 2 * mm))

    document.build(story)
    return output.getvalue()


def _data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
