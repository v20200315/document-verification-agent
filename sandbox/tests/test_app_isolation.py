from pathlib import Path

SANDBOX_DIR = Path(__file__).parents[1]


def test_simple_rag_does_not_import_ccc_application_code() -> None:
    simple_rag_source = "\n".join(
        path.read_text() for path in (SANDBOX_DIR / "app" / "simple_rag").glob("*.py")
    )
    forbidden_imports = (
        "sandbox.app.pipeline_service",
        "sandbox.app.ui_components",
        "sandbox.src.classifier",
        "sandbox.src.extractor",
        "sandbox.src.info_checker",
        "sandbox.src.loaders",
        "sandbox.src.pipeline",
        "sandbox.src.qr",
        "sandbox.src.certificate_fields",
        "sandbox.src.cqc_web",
        "sandbox.src.schemas",
        "sandbox.src.tampering",
    )

    assert not any(dependency in simple_rag_source for dependency in forbidden_imports)
    assert "sandbox.app.verify_test_report" not in simple_rag_source


def test_dashboard_and_ccc_do_not_import_other_applications() -> None:
    dashboard = (SANDBOX_DIR / "app" / "app_pages" / "dashboard.py").read_text()
    ccc = (SANDBOX_DIR / "app" / "app_pages" / "ccc_verification.py").read_text()

    assert "sandbox.app.simple_rag" not in dashboard
    assert "sandbox.app.pipeline_service" not in dashboard
    assert "sandbox.app.ui_components" not in dashboard
    assert "sandbox.app.simple_rag" not in ccc
    assert "sandbox.app.image_pdf_to_text" not in dashboard
    assert "sandbox.app.image_pdf_to_text" not in ccc
    assert "sandbox.app.verify_test_report" not in dashboard
    assert "sandbox.app.verify_test_report" not in ccc


def test_image_pdf_converter_does_not_import_other_applications() -> None:
    converter_source = "\n".join(
        path.read_text()
        for path in (SANDBOX_DIR / "app" / "image_pdf_to_text").glob("*.py")
    )

    assert "sandbox.app.simple_rag" not in converter_source
    assert "sandbox.app.pipeline_service" not in converter_source
    assert "sandbox.app.ui_components" not in converter_source
    assert "sandbox.src.schemas" not in converter_source
    assert "sandbox.app.verify_test_report" not in converter_source


def test_verify_test_report_does_not_import_other_applications() -> None:
    feature_source = "\n".join(
        path.read_text()
        for path in (SANDBOX_DIR / "app" / "verify_test_report").glob("*.py")
    )
    page_source = (
        SANDBOX_DIR / "app" / "app_pages" / "verify_test_report.py"
    ).read_text()
    forbidden_imports = (
        "sandbox.app.pipeline_service",
        "sandbox.app.ui_components",
        "sandbox.app.simple_rag",
        "sandbox.app.image_pdf_to_text",
        "sandbox.src.classifier",
        "sandbox.src.extractor",
        "sandbox.src.info_checker",
        "sandbox.src.loaders",
        "sandbox.src.pipeline",
        "sandbox.src.qr",
        "sandbox.src.certificate_fields",
        "sandbox.src.cqc_web",
        "sandbox.src.schemas",
        "sandbox.src.tampering",
        "DocumentCategory",
    )

    assert not any(dependency in feature_source for dependency in forbidden_imports)
    assert not any(dependency in page_source for dependency in forbidden_imports)
