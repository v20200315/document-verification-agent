from __future__ import annotations

import base64
import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from sandbox.src.errors import DocumentLoadError
from sandbox.src.schemas import LoadedDocument, PageInput

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}
MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class DocumentLoader:
    """Turn files into page units while keeping OCR routing provider-neutral."""

    def __init__(
        self,
        scanned_text_threshold: int = 40,
        pdf_render_dpi: int = 180,
    ) -> None:
        self.scanned_text_threshold = scanned_text_threshold
        self.pdf_render_dpi = pdf_render_dpi

    def load(self, file_path: str | Path) -> LoadedDocument:
        path = Path(file_path).expanduser().resolve()
        self._validate_path(path)
        if path.suffix.lower() in IMAGE_SUFFIXES:
            return self._load_image(path)
        return self._load_pdf(path)

    @staticmethod
    def _validate_path(path: Path) -> None:
        if not path.is_file():
            raise DocumentLoadError(f"Input file does not exist: {path}")
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise DocumentLoadError(
                f"Unsupported file extension {path.suffix!r}; "
                f"expected one of: {supported}"
            )

    def _load_image(self, path: Path) -> LoadedDocument:
        try:
            # Verification catches corrupt or mislabeled files before an API call.
            with Image.open(path) as image:
                image.verify()
            data = path.read_bytes()
        except (OSError, UnidentifiedImageError) as exc:
            raise DocumentLoadError(
                f"Unable to decode image {path.name}: {exc}"
            ) from exc

        return LoadedDocument(
            file_name=path.name,
            file_type="image",
            pages=[
                PageInput(
                    page_number=1,
                    route="vision",
                    image_data_url=_data_url(data, MIME_BY_SUFFIX[path.suffix.lower()]),
                )
            ],
        )

    def _load_pdf(self, path: Path) -> LoadedDocument:
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise DocumentLoadError(f"PDF {path.name} is password-protected.")
            page_texts = [page.extract_text() or "" for page in reader.pages]
        except DocumentLoadError:
            raise
        except Exception as exc:
            raise DocumentLoadError(f"Unable to read PDF {path.name}: {exc}") from exc

        if not page_texts:
            raise DocumentLoadError(f"PDF {path.name} contains no pages.")

        pages: list[PageInput] = []
        scanned_indices = {
            index
            for index, text in enumerate(page_texts)
            if len("".join(text.split())) < self.scanned_text_threshold
        }
        rendered_pages = self._render_pdf_pages(path, scanned_indices)

        for index, text in enumerate(page_texts):
            page_number = index + 1
            if index in scanned_indices:
                pages.append(
                    PageInput(
                        page_number=page_number,
                        route="vision",
                        image_data_url=rendered_pages[index],
                    )
                )
            else:
                pages.append(
                    PageInput(
                        page_number=page_number,
                        route="text",
                        text=text.strip(),
                    )
                )

        return LoadedDocument(
            file_name=path.name,
            file_type="pdf",
            pages=pages,
            page_count=len(pages),
        )

    def _render_pdf_pages(self, path: Path, page_indices: set[int]) -> dict[int, str]:
        if not page_indices:
            return {}

        rendered: dict[int, str] = {}
        document = None
        try:
            document = pdfium.PdfDocument(str(path))
            scale = self.pdf_render_dpi / 72
            for index in sorted(page_indices):
                page = document[index]
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                rendered[index] = _data_url(buffer.getvalue(), "image/png")
                image.close()
                bitmap.close()
                page.close()
        except Exception as exc:
            raise DocumentLoadError(
                f"Unable to render scanned pages in {path.name}: {exc}"
            ) from exc
        finally:
            if document is not None:
                document.close()

        return rendered


def _data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
