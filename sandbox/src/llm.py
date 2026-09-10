from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from tenacity import Retrying, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_exponential_jitter

from sandbox.src.config import Settings


class Invokable(Protocol):
    def invoke(self, input: Any) -> Any: ...


class MalformedModelResponse(ValueError):
    """Marks parse failures as retryable without retrying programmer errors."""


def build_models(settings: Settings) -> tuple[ChatOpenAI, ChatOpenAI]:
    common = {
        "api_key": settings.api_key,
        "base_url": settings.base_url,
        "temperature": 0,
        "timeout": settings.request_timeout_seconds,
        # Tenacity owns retries so behavior is identical for parsing failures.
        "max_retries": 0,
    }
    return (
        ChatOpenAI(model=settings.text_model, **common),
        ChatOpenAI(model=settings.vision_model, **common),
    )


def invoke_with_retry[T](call: Callable[[], T], attempts: int) -> T:
    retryer = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=1, max=8),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    return retryer(call)


def response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        text = "\n".join(parts).strip()
    else:
        text = ""

    if not text:
        raise MalformedModelResponse("The model returned empty text.")
    return text


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            MalformedModelResponse,
        ),
    ):
        return True

    if exc.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
    }:
        return True

    status_code = getattr(exc, "status_code", None)
    return isinstance(status_code, int) and (status_code == 429 or status_code >= 500)
