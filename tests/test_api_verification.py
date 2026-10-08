from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.errors import DocumentTypeError, QueueTimeoutError, VerificationSystemError
from app.main import app
from sandbox.src.errors import DocumentLoadError


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_ccc_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.verification.is_api_configured",
        lambda: False,
    )
    client = TestClient(app)
    response = client.post(
        "/verify/ccc",
        files={"file": ("cert.jpg", b"not-empty", "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json()["status_code"] == 503
    assert response.json()["error"] == "missing_api_key"


def test_verify_ccc_success_returns_markdown_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sandbox.src.schemas import ProcessedDocument

    monkeypatch.setattr("app.api.verification.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.verification.process_uploaded_document",
        lambda _name, _data: ProcessedDocument(
            file_md5="0123456789abcdef0123456789abcdef",
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/verify/ccc",
        files={"file": ("cert.jpg", b"not-empty", "image/jpeg")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status_code"] == 200
    assert payload["report"].startswith("# CCC 证书核验最终报告\n")


def test_verify_ccc_rejects_non_ccc_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.verification.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.verification.process_uploaded_document",
        lambda _name, _data: (_ for _ in ()).throw(
            DocumentTypeError("上传文件不是 CCC 证书，当前识别类型为：Other。")
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/verify/ccc",
        files={"file": ("other.jpg", b"not-empty", "image/jpeg")},
    )
    assert response.status_code == 422
    assert response.json() == {
        "status_code": 422,
        "error": "not_ccc_document",
        "detail": "上传文件不是 CCC 证书，当前识别类型为：Other。",
    }


def test_verify_ccc_reports_system_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.verification.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.verification.process_uploaded_document",
        lambda _name, _data: (_ for _ in ()).throw(
            VerificationSystemError("Qwen extraction failed")
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/verify/ccc",
        files={"file": ("cert.jpg", b"not-empty", "image/jpeg")},
    )
    assert response.status_code == 500
    assert response.json()["status_code"] == 500
    assert response.json()["error"] == "system_error"


def test_verify_ccc_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.verification.is_api_configured", lambda: True)
    monkeypatch.setattr("app.api.verification.CCC_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("app.api.verification.CCC_QUEUE_WAIT_SECONDS", 1)

    def _slow(_name: str, _data: bytes) -> None:
        import time

        time.sleep(0.2)

    monkeypatch.setattr(
        "app.api.verification.process_uploaded_document",
        _slow,
    )
    client = TestClient(app)
    response = client.post(
        "/verify/ccc",
        files={"file": ("cert.jpg", b"not-empty", "image/jpeg")},
    )
    assert response.status_code == 504
    assert response.json()["status_code"] == 504
    assert response.json()["error"] == "timeout"
    assert "1 分钟" in response.json()["detail"]


def test_verify_test_report_rejects_other_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.verification.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.verification.verify_uploaded_test_report",
        lambda _name, _data: (_ for _ in ()).throw(
            DocumentTypeError("上传文件不是可核验的检测报告（产品类别为 Other）。")
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/verify/test-report",
        files={"file": ("report.pdf", b"not-empty", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["status_code"] == 422
    assert response.json()["error"] == "not_test_report"


def test_verify_ccc_rejects_empty_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.verification.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.verification.process_uploaded_document",
        lambda _name, _data: (_ for _ in ()).throw(
            DocumentLoadError("The uploaded file is empty.")
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/verify/ccc",
        files={"file": ("cert.jpg", b"not-empty", "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_upload"


def test_verify_ccc_reports_queue_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.verification.is_api_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.verification.run_with_queue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            QueueTimeoutError("CCC 核验排队超时，请稍后重试。")
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/verify/ccc",
        files={"file": ("cert.jpg", b"not-empty", "image/jpeg")},
    )
    assert response.status_code == 429
    assert response.json()["status_code"] == 429
    assert response.json()["error"] == "queue_timeout"
