from __future__ import annotations


class DocumentTypeError(ValueError):
    """Raised when the uploaded file is not the expected document type."""


class VerificationTimeoutError(TimeoutError):
    """Raised when verification exceeds the allowed time."""


class VerificationSystemError(RuntimeError):
    """Raised when verification fails due to an internal or pipeline error."""
