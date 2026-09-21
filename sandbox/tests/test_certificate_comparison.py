from __future__ import annotations

from sandbox.src.certificate_comparison import (
    compare_certificate_sources,
    format_comparison_report_plain_text,
)
from sandbox.src.schemas import (
    CccCertificateFields,
    CqcWebComparisonOutcome,
    InfoCheckStatus,
)


def test_compare_certificate_sources_reports_all_matches() -> None:
    fields = CccCertificateFields(
        certificate_number="2025010703748148",
        certificate_status="有效",
        manufacturer="浙江德富新能源技术有限公司",
    )

    report = compare_certificate_sources(
        image_certificate=fields,
        website_certificate=fields.model_copy(),
        website_source_url="https://www.cqc.com.cn/example",
    )

    assert report is not None
    assert report.status == InfoCheckStatus.ALL_MATCHED
    assert all(
        item.outcome == CqcWebComparisonOutcome.MATCH for item in report.comparisons
    )


def test_compare_certificate_sources_detects_mismatch() -> None:
    report = compare_certificate_sources(
        image_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            product_name="产品 A",
        ),
        website_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            product_name="产品 B",
        ),
        website_source_url="https://www.cqc.com.cn/example",
    )

    assert report is not None
    assert report.status == InfoCheckStatus.MISMATCH_FOUND
    product_item = next(
        item for item in report.comparisons if item.field_name.value == "Product name"
    )
    assert product_item.outcome == CqcWebComparisonOutcome.MISMATCH


def test_compare_certificate_sources_skips_without_website_url() -> None:
    report = compare_certificate_sources(
        image_certificate=CccCertificateFields(certificate_number="2025010703748148"),
        website_certificate=None,
        website_source_url=None,
    )

    assert report is None


def test_format_comparison_report_plain_text_includes_field_lines() -> None:
    report = compare_certificate_sources(
        image_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            manufacturer="浙江德富新能源技术有限公司",
        ),
        website_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            manufacturer="浙江德富新能源技术有限公司",
        ),
        website_source_url="https://www.cqc.com.cn/example",
    )

    assert report is not None
    text = format_comparison_report_plain_text(report)

    assert "Status / 状态: All Matched" in text
    assert "Certificate number: Match" in text
    assert "2025010703748148" in text
