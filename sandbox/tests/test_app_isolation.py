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
        "sandbox.src.schemas",
        "sandbox.src.tampering",
    )

    assert not any(dependency in simple_rag_source for dependency in forbidden_imports)


def test_dashboard_and_ccc_do_not_import_other_applications() -> None:
    dashboard = (SANDBOX_DIR / "app" / "app_pages" / "dashboard.py").read_text()
    ccc = (SANDBOX_DIR / "app" / "app_pages" / "ccc_verification.py").read_text()

    assert "sandbox.app.simple_rag" not in dashboard
    assert "sandbox.app.pipeline_service" not in dashboard
    assert "sandbox.app.ui_components" not in dashboard
    assert "sandbox.app.simple_rag" not in ccc
