"""Domain exceptions exposed by the sandbox pipeline."""


class DocumentPipelineError(RuntimeError):
    """Base error for failures callers can handle without provider details."""


class ConfigurationError(DocumentPipelineError):
    """Raised when required runtime configuration is missing or invalid."""


class DocumentLoadError(DocumentPipelineError):
    """Raised when an input cannot be validated or decoded."""


class ExtractionError(DocumentPipelineError):
    """Raised when complete content extraction cannot be completed."""
