from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentCategory(StrEnum):
    AUTHORIZATION = "Authorization Document"
    CCC_CERTIFICATION = "CCC Certification Document"
    OTHER = "Other"


class PageInput(BaseModel):
    """Internal page unit keeps routing separate from provider invocation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    page_number: int = Field(ge=1)
    route: Literal["text", "vision"]
    text: str | None = None
    image_data_url: str | None = None


class LoadedDocument(BaseModel):
    file_name: str
    file_type: Literal["image", "pdf"]
    pages: list[PageInput] = Field(min_length=1)
    page_count: int | None = Field(default=None, ge=1)


class ExtractedPage(BaseModel):
    page_number: int = Field(ge=1)
    content: str = Field(min_length=1)


class ClassificationResult(BaseModel):
    """Closed category enum prevents unrecognized labels reaching callers."""

    doc_category: DocumentCategory
    category_confidence: float | None = Field(default=None, ge=0, le=1)
    category_reasoning: str | None = None


class DocumentResult(BaseModel):
    file_name: str
    file_type: Literal["image", "pdf"]
    doc_category: DocumentCategory
    category_confidence: float | None = Field(default=None, ge=0, le=1)
    category_reasoning: str | None = None
    full_content: str = Field(min_length=1)
    page_count: int | None = Field(default=None, ge=1)
