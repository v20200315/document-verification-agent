from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from sandbox.src.llm import (
    MalformedModelResponse,
    invoke_with_retry,
)
from sandbox.src.schemas import ClassificationResult, DocumentCategory

CLASSIFICATION_PROMPT = """Classify the transcribed document into exactly one:
- Authorization Document: authorization letters/certificates, agency,
  dealership, representation, or permission documents (授权文件).
- CCC Certification Document: China Compulsory Certification certificates
  or documents explicitly proving CCC/3C certification (CCC认证文件).
- Other: anything that does not satisfy either definition.

Base the decision only on the supplied content. Return the category, a
self-assessed confidence from 0 to 1, and concise evidence-based reasoning."""


class DocumentClassifier:
    """Use a separate structured call so extraction remains verbatim."""

    def __init__(self, model: Any, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts
        self.structured_model = model.with_structured_output(
            ClassificationResult,
            method="json_schema",
            strict=True,
            include_raw=True,
        )

    def classify(self, full_content: str) -> ClassificationResult:
        try:
            return invoke_with_retry(
                lambda: self._classify_once(full_content),
                self.max_attempts,
            )
        except Exception as exc:  # noqa: BLE001
            # Extraction remains useful even when provider JSON is unavailable.
            return ClassificationResult(
                doc_category=DocumentCategory.OTHER,
                category_reasoning=(
                    "Classification was unavailable after retries: "
                    f"{exc.__class__.__name__}: {exc}"
                ),
            )

    def _classify_once(self, full_content: str) -> ClassificationResult:
        try:
            response = self.structured_model.invoke(
                [
                    SystemMessage(content=CLASSIFICATION_PROMPT),
                    HumanMessage(content=full_content),
                ]
            )
            parsed = _parsed_value(response)
            if isinstance(parsed, ClassificationResult):
                return parsed
            return ClassificationResult.model_validate(parsed)
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            raise MalformedModelResponse(
                f"Invalid structured classification: {exc}"
            ) from exc


def _parsed_value(response: Any) -> Any:
    if not isinstance(response, dict) or "parsed" not in response:
        return response
    if response.get("parsing_error") is not None:
        raise MalformedModelResponse(str(response["parsing_error"]))
    if response["parsed"] is None:
        raise MalformedModelResponse("The model returned no parsed classification.")
    return response["parsed"]
