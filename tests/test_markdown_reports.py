from __future__ import annotations

from datetime import date

from app.reports.markdown_reports import (
    build_ccc_final_markdown,
    build_test_report_final_markdown,
)
from sandbox.app.verify_test_report.backend import (
    ComplianceReport,
    ComplianceStatus,
    ProductCategory,
    RuleFinding,
    TestReportResult,
)
from sandbox.src.certificate_comparison import compare_certificate_sources
from sandbox.src.schemas import CccCertificateFields, ProcessedDocument


def test_build_ccc_final_markdown_includes_comparison_only() -> None:
    fields = CccCertificateFields(
        certificate_number="2025010703748148",
        models_and_specifications="DF-CTS064",
        applicable_standards="GB 4706.1",
        valid_until="2029 年 07 月 18 日",
    )
    comparison = compare_certificate_sources(
        image_certificate=fields,
        website_certificate=fields.model_copy(update={"certificate_status": "有效"}),
        website_source_url="https://www.cqc.com.cn/example",
        reference_date=date(2026, 9, 21),
    )
    processed = ProcessedDocument(
        file_md5="0123456789abcdef0123456789abcdef",
        certificate=fields,
        cqc_comparison_report=comparison,
    )

    markdown = build_ccc_final_markdown(processed)

    assert markdown.startswith("# CCC 证书核验最终报告\n")
    assert "## 字段比对" in markdown
    assert "|" not in markdown
    assert "certificate_number" not in markdown
    assert "qr_payloads" not in markdown


def test_build_test_report_final_markdown_uses_compliance_section() -> None:
    classification = TestReportResult(
        file_name="report.pdf",
        page_count=3,
        product_category=ProductCategory.HEAT_FAN,
        category_reasoning="报告标题与检测项目符合热风机类别。",
        full_content="report text",
    )
    compliance = ComplianceReport(
        product_category=ProductCategory.HEAT_FAN,
        overall_status=ComplianceStatus.PASS,
        summary="全部规则通过。",
        findings=[
            RuleFinding(
                rule_number=1,
                rule_text="规则一",
                status=ComplianceStatus.PASS,
                evidence="报告中有对应描述。",
            )
        ],
    )

    markdown = build_test_report_final_markdown(classification, compliance, None)

    assert markdown.startswith("# 检测报告核验最终报告\n")
    assert "## 规则核验" in markdown
    assert "full_content" not in markdown
