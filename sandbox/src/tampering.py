from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from langchain_core.messages import HumanMessage, SystemMessage
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from sandbox.src.config import Settings
from sandbox.src.errors import TamperingAnalysisError
from sandbox.src.llm import (
    MalformedModelResponse,
    build_models,
    invoke_with_retry,
)
from sandbox.src.schemas import (
    PageTamperingAssessment,
    TamperingReport,
    TamperingRisk,
    TamperingStatus,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}
LIMITATIONS = (
    "This is an AI-assisted visual tampering-risk assessment, not proof of "
    "authenticity. Scanning, resizing, compression, and image enhancement can "
    "create false positives or conceal edits. Confirm authenticity through "
    "digital-signature and official registry checks."
)

SYSTEM_PROMPT = """You perform cautious visual document-tampering analysis.
Inspect the supplied page for localized inconsistencies such as mismatched
fonts, alignment, spacing, colors, pixel sharpness, compression boundaries,
overlays, altered identifiers or dates, duplicated regions, irregular seals,
and QR-code placement. Report only visible evidence; never infer authenticity
from professional appearance. Normal scanning, shadows, perspective,
compression, and photography artifacts must not be labeled as tampering
without specific evidence. If image quality is insufficient, return an
Inconclusive risk. This checkpoint does not validate registries, issuers,
certificate status, cryptographic signatures, or product scope."""


class TamperingAnalyzer:
    """Analyze original page pixels separately from content classification."""

    def __init__(
        self,
        vision_model: Any,
        max_attempts: int = 3,
        pdf_render_dpi: int = 180,
    ) -> None:
        self.max_attempts = max_attempts
        self.pdf_render_dpi = pdf_render_dpi
        self.structured_model = vision_model.with_structured_output(
            PageTamperingAssessment,
            method="json_schema",
            strict=True,
            include_raw=True,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> TamperingAnalyzer:
        _, vision_model = build_models(settings)
        return cls(
            vision_model=vision_model,
            max_attempts=settings.max_retries,
            pdf_render_dpi=settings.pdf_render_dpi,
        )

    @classmethod
    def from_env(cls) -> TamperingAnalyzer:
        return cls.from_settings(Settings.from_env())

    def analyze(self, file_path: str | Path) -> TamperingReport:
        path = Path(file_path).expanduser().resolve()
        visual_pages = self._load_visual_pages(path)
        assessments: list[PageTamperingAssessment] = []

        for page_number, image_data_url in visual_pages:
            try:
                assessment = invoke_with_retry(
                    lambda page_number=page_number, image_data_url=image_data_url: (
                        self._analyze_page(page_number, image_data_url)
                    ),
                    self.max_attempts,
                )
            except Exception as exc:
                raise TamperingAnalysisError(
                    f"Tampering analysis failed for page {page_number} of "
                    f"{path.name}: {exc}"
                ) from exc
            assessments.append(assessment)

        return _assemble_report(assessments)

    def _analyze_page(
        self, page_number: int, image_data_url: str
    ) -> PageTamperingAssessment:
        try:
            response = self.structured_model.invoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": (
                                    f"Analyze page {page_number}. Every finding "
                                    "must use this page number and identify a "
                                    "specific location and visible observation."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url},
                            },
                        ]
                    ),
                ]
            )
            parsed = _parsed_value(response)
            assessment = (
                parsed
                if isinstance(parsed, PageTamperingAssessment)
                else PageTamperingAssessment.model_validate(parsed)
            )
            # The caller owns page numbering; do not trust a model-generated index.
            assessment.page_number = page_number
            for finding in assessment.findings:
                finding.page_number = page_number
            return assessment
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            raise MalformedModelResponse(
                f"Invalid structured tampering response: {exc}"
            ) from exc

    def _load_visual_pages(self, path: Path) -> list[tuple[int, str]]:
        if not path.is_file():
            raise TamperingAnalysisError(f"Input file does not exist: {path}")
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise TamperingAnalysisError(
                f"Unsupported tampering-analysis file type: {suffix}"
            )
        if suffix in IMAGE_SUFFIXES:
            return [(1, _image_file_data_url(path))]
        return self._render_pdf(path)

    def _render_pdf(self, path: Path) -> list[tuple[int, str]]:
        document = None
        pages: list[tuple[int, str]] = []
        try:
            document = pdfium.PdfDocument(str(path))
            if len(document) == 0:
                raise TamperingAnalysisError(f"PDF {path.name} contains no pages.")
            scale = self.pdf_render_dpi / 72
            for index in range(len(document)):
                page = bitmap = image = None
                try:
                    page = document[index]
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil()
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    pages.append(
                        (
                            index + 1,
                            _data_url(buffer.getvalue(), "image/png"),
                        )
                    )
                finally:
                    if image is not None:
                        image.close()
                    if bitmap is not None:
                        bitmap.close()
                    if page is not None:
                        page.close()
        except TamperingAnalysisError:
            raise
        except Exception as exc:
            raise TamperingAnalysisError(
                f"Unable to render {path.name} for tampering analysis: {exc}"
            ) from exc
        finally:
            if document is not None:
                document.close()
        return pages


def _image_file_data_url(path: Path) -> str:
    try:
        with Image.open(path) as image:
            image.verify()
        data = path.read_bytes()
    except (OSError, UnidentifiedImageError) as exc:
        raise TamperingAnalysisError(
            f"Unable to decode image {path.name}: {exc}"
        ) from exc
    mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return _data_url(data, mime_type)


def _data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _parsed_value(response: Any) -> Any:
    if not isinstance(response, dict) or "parsed" not in response:
        return response
    if response.get("parsing_error") is not None:
        raise MalformedModelResponse(str(response["parsing_error"]))
    if response["parsed"] is None:
        raise MalformedModelResponse(
            "The model returned no parsed tampering assessment."
        )
    return response["parsed"]


def _assemble_report(
    assessments: list[PageTamperingAssessment],
) -> TamperingReport:
    findings = [
        finding for assessment in assessments for finding in assessment.findings
    ]
    risk_rank = {
        TamperingRisk.LOW: 0,
        TamperingRisk.INCONCLUSIVE: 1,
        TamperingRisk.MEDIUM: 2,
        TamperingRisk.HIGH: 3,
    }
    risk_level = max(
        (assessment.risk_level for assessment in assessments),
        key=risk_rank.__getitem__,
    )
    suspected_values = [assessment.suspected_tampering for assessment in assessments]
    suspected = (
        True
        if True in suspected_values
        else False
        if all(value is False for value in suspected_values)
        else None
    )

    if risk_level in {TamperingRisk.MEDIUM, TamperingRisk.HIGH}:
        status = TamperingStatus.REVIEW_REQUIRED
    elif risk_level is TamperingRisk.INCONCLUSIVE:
        status = TamperingStatus.INCONCLUSIVE
    else:
        status = TamperingStatus.NO_OBVIOUS_INDICATORS

    summary = " ".join(
        f"Page {item.page_number}: {item.summary}" for item in assessments
    )
    return TamperingReport(
        status=status,
        risk_level=risk_level,
        suspected_tampering=suspected,
        findings=findings,
        summary=summary,
        limitations=LIMITATIONS,
        pages_analyzed=len(assessments),
    )
