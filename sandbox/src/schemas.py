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


class TamperingSeverity(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class TamperingRisk(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    INCONCLUSIVE = "Inconclusive"


class TamperingStatus(StrEnum):
    NO_OBVIOUS_INDICATORS = "No Obvious Indicators"
    REVIEW_REQUIRED = "Review Required"
    INCONCLUSIVE = "Inconclusive"


class TamperingFinding(BaseModel):
    page_number: int = Field(ge=1)
    location: str = Field(min_length=1)
    observation: str = Field(min_length=1)
    severity: TamperingSeverity


class PageTamperingAssessment(BaseModel):
    page_number: int = Field(ge=1)
    risk_level: TamperingRisk
    suspected_tampering: bool | None = None
    findings: list[TamperingFinding] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TamperingReport(BaseModel):
    """A visual-risk checkpoint, deliberately not an authenticity verdict."""

    check_type: Literal["Visual Tampering Analysis"] = "Visual Tampering Analysis"
    status: TamperingStatus
    risk_level: TamperingRisk
    suspected_tampering: bool | None = None
    findings: list[TamperingFinding] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    pages_analyzed: int = Field(ge=1)


class CertificateFieldName(StrEnum):
    CERTIFICATE_NUMBER = "Certificate number"
    STATUS = "Certificate status"
    HOLDER = "Certificate holder"
    MANUFACTURER = "Manufacturer"
    FACTORY = "Production factory"
    PRODUCT = "Product name"
    MODEL = "Models and specifications"
    STANDARDS = "Applicable standards"
    ISSUING_BODY = "Issuing certification body"
    ISSUE_DATE = "Issue date"
    VALID_UNTIL = "Valid until"


class CNCAEvidence(BaseModel):
    """Normalized fields visible in user-provided CNCA result screenshots."""

    certificate_number: str | None = None
    certificate_status: str | None = None
    certificate_holder: str | None = None
    manufacturer: str | None = None
    production_factory: str | None = None
    product_name: str | None = None
    models_and_specifications: str | None = None
    applicable_standards: str | None = None
    issuing_certification_body: str | None = None
    issue_date: str | None = None
    valid_until: str | None = None
    extraction_notes: str | None = None
    source_image_count: int = Field(ge=1)


class InfoComparisonOutcome(StrEnum):
    MATCH = "Match"
    MISMATCH = "Mismatch"
    MISSING_SOURCE = "Missing from certificate"
    MISSING_CNCA = "Missing from CNCA evidence"
    INCONCLUSIVE = "Inconclusive"


class InfoCheckStatus(StrEnum):
    ALL_MATCHED = "All Matched"
    MISMATCH_FOUND = "Mismatch Found"
    INCONCLUSIVE = "Inconclusive"


class InfoComparisonItem(BaseModel):
    field_name: CertificateFieldName
    source_value: str | None = None
    cnca_value: str | None = None
    outcome: InfoComparisonOutcome
    explanation: str = Field(min_length=1)


class InfoComparisonReport(BaseModel):
    """Compares certificate text with screenshot evidence, not CNCA directly."""

    check_type: Literal["CNCA Screenshot Information Comparison"] = (
        "CNCA Screenshot Information Comparison"
    )
    status: InfoCheckStatus
    comparisons: list[InfoComparisonItem] = Field(min_length=1)
    summary: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    evidence_image_count: int = Field(ge=1)
