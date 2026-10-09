from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.errors import (
    DocumentTypeError,
    QueueBusyError,
    VerificationSystemError,
    VerificationTimeoutError,
)
from app.models.responses import MarkdownReportResponse
from app.queue_control import (
    CCC_TIMEOUT_SECONDS,
    TEST_REPORT_TIMEOUT_SECONDS,
    ccc_limiter,
    run_with_queue,
    test_report_limiter,
)
from app.reports.markdown_reports import (
    build_ccc_final_markdown,
    build_test_report_final_markdown,
)
from app.services.ccc_verification import is_api_configured, process_uploaded_document
from app.services.test_report_verification import verify_uploaded_test_report
from sandbox.app.image_pdf_to_text.backend import ImagePDFConversionError
from sandbox.app.verify_test_report.backend import TestReportError
from sandbox.src.errors import DocumentLoadError

router = APIRouter(prefix="/verify", tags=["verification"])

BUSY_REPORT = "# AI请求数量已达最大值，请稍后再试。"

ERROR_RESPONSES = {
    400: {"description": "Invalid upload"},
    422: {"description": "Not the expected document type"},
    500: {"description": "System error"},
    503: {"description": "API key is not configured"},
    504: {"description": "Verification timed out"},
}


def _require_api_key() -> JSONResponse | None:
    if not is_api_configured():
        return _error_response(
            503,
            "missing_api_key",
            "DASHSCOPE_API_KEY is not configured. "
            "Set it in the environment or project-root .env.",
        )
    return None


def _error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status_code": status_code, "error": error, "detail": detail},
    )


@router.post(
    "/ccc",
    response_model=MarkdownReportResponse,
    responses=ERROR_RESPONSES,
)
async def verify_ccc(
    file: UploadFile = File(..., description="CCC certificate PDF or image"),  # noqa: B008
) -> MarkdownReportResponse | JSONResponse:
    """Verify a CCC document and return status_code plus the final Markdown report."""
    if missing_key := _require_api_key():
        return missing_key
    file_name = file.filename or "upload.pdf"
    data = await file.read()
    try:
        processed = await run_with_queue(
            process_uploaded_document,
            file_name,
            data,
            limiter=ccc_limiter(),
            timeout_seconds=CCC_TIMEOUT_SECONDS,
            busy_message=BUSY_REPORT,
            timeout_message="CCC 核验超时（超过 1 分钟）。",
        )
    except DocumentLoadError as exc:
        return _error_response(400, "invalid_upload", str(exc))
    except DocumentTypeError as exc:
        return _error_response(422, "not_ccc_document", str(exc))
    except QueueBusyError:
        return MarkdownReportResponse(status_code=200, report=BUSY_REPORT)
    except VerificationTimeoutError as exc:
        return _error_response(504, "timeout", str(exc))
    except VerificationSystemError as exc:
        return _error_response(500, "system_error", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error_response(500, "system_error", f"{exc.__class__.__name__}: {exc}")

    return MarkdownReportResponse(
        status_code=200,
        report=build_ccc_final_markdown(processed),
    )


@router.post(
    "/test-report",
    response_model=MarkdownReportResponse,
    responses=ERROR_RESPONSES,
)
async def verify_test_report(
    file: UploadFile = File(..., description="Test report PDF"),  # noqa: B008
) -> MarkdownReportResponse | JSONResponse:
    """Verify a test report PDF and return status_code plus the final Markdown report."""
    if missing_key := _require_api_key():
        return missing_key
    file_name = file.filename or "upload.pdf"
    data = await file.read()
    try:
        classification, compliance, validation_note = await run_with_queue(
            verify_uploaded_test_report,
            file_name,
            data,
            limiter=test_report_limiter(),
            timeout_seconds=TEST_REPORT_TIMEOUT_SECONDS,
            busy_message=BUSY_REPORT,
            timeout_message="检测报告核验超时（超过 10 分钟）。",
        )
    except DocumentLoadError as exc:
        return _error_response(400, "invalid_upload", str(exc))
    except TestReportError as exc:
        return _error_response(400, "invalid_upload", str(exc))
    except ImagePDFConversionError as exc:
        return _error_response(500, "system_error", f"图片型 PDF OCR 失败：{exc}")
    except DocumentTypeError as exc:
        return _error_response(422, "not_test_report", str(exc))
    except QueueBusyError:
        return MarkdownReportResponse(status_code=200, report=BUSY_REPORT)
    except VerificationTimeoutError as exc:
        return _error_response(504, "timeout", str(exc))
    except VerificationSystemError as exc:
        return _error_response(500, "system_error", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error_response(500, "system_error", f"{exc.__class__.__name__}: {exc}")

    return MarkdownReportResponse(
        status_code=200,
        report=build_test_report_final_markdown(
            classification,
            compliance,
            validation_note,
        ),
    )
