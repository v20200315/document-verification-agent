from __future__ import annotations

import os
from dataclasses import dataclass

from sandbox.src.errors import ConfigurationError

DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True, slots=True)
class Settings:
    """Centralize provider and routing knobs so models can be swapped safely."""

    api_key: str
    base_url: str = DEFAULT_DASHSCOPE_BASE_URL
    vision_model: str = "qwen3-vl-plus"
    text_model: str = "qwen-plus"
    request_timeout_seconds: float = 120.0
    max_retries: int = 3
    scanned_text_threshold: int = 40
    pdf_render_dpi: int = 180

    @classmethod
    def from_env(cls) -> Settings:
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise ConfigurationError(
                "DASHSCOPE_API_KEY is not set. Export a DashScope API key "
                "before running the document pipeline."
            )

        return cls(
            api_key=api_key,
            base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_DASHSCOPE_BASE_URL).rstrip(
                "/"
            ),
            vision_model=os.getenv("QWEN_VISION_MODEL", "qwen3-vl-plus"),
            text_model=os.getenv("QWEN_TEXT_MODEL", "qwen-plus"),
            request_timeout_seconds=_float_env("DASHSCOPE_TIMEOUT_SECONDS", 120.0),
            max_retries=_int_env("DASHSCOPE_MAX_RETRIES", 3),
            scanned_text_threshold=_int_env("PDF_SCANNED_TEXT_THRESHOLD", 40),
            pdf_render_dpi=_int_env("PDF_RENDER_DPI", 180),
        )


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return parsed


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return parsed
