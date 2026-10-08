from __future__ import annotations

from pydantic import BaseModel, Field


class MarkdownReportResponse(BaseModel):
    """Successful verification output with HTTP status and Markdown report."""

    status_code: int = Field(default=200, description="HTTP status code.")
    report: str = Field(min_length=1, description="Final verification report in Markdown.")
