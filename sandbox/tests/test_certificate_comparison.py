from __future__ import annotations

from datetime import date

from sandbox.src.certificate_comparison import (
    compare_certificate_sources,
    format_comparison_report_plain_text,
)
from sandbox.src.schemas import (
    CccCertificateFields,
    CqcVerificationCheckName,
    CqcWebComparisonOutcome,
    CqcWebVerificationOutcome,
    InfoCheckStatus,
)


def _matched_fields() -> CccCertificateFields:
    return CccCertificateFields(
        certificate_number="2025010703748148",
        models_and_specifications="DF-CTS064 I /04 220V～ 50Hz R410A",
        applicable_standards="GB 17625.1–2022；GB 4343.1–2018",
        valid_until="2029 年 07 月 18 日",
    )


def test_compare_certificate_sources_reports_all_matches_and_passing_checks() -> None:
    image = _matched_fields()
    website = image.model_copy(update={"certificate_status": "有效"})

    report = compare_certificate_sources(
        image_certificate=image,
        website_certificate=website,
        website_source_url="https://www.cqc.com.cn/example",
        reference_date=date(2026, 9, 21),
    )

    assert report is not None
    assert report.status == InfoCheckStatus.ALL_MATCHED
    assert len(report.comparisons) == 3
    assert all(
        item.outcome == CqcWebComparisonOutcome.MATCH for item in report.comparisons
    )
    assert all(
        item.outcome == CqcWebVerificationOutcome.PASS for item in report.verifications
    )


def test_compare_certificate_sources_detects_model_mismatch() -> None:
    report = compare_certificate_sources(
        image_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            models_and_specifications="Model A",
            applicable_standards="GB 4706.1",
            valid_until="2029 年 07 月 18 日",
        ),
        website_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            models_and_specifications="Model B",
            applicable_standards="GB 4706.1",
            certificate_status="有效",
        ),
        website_source_url="https://www.cqc.com.cn/example",
        reference_date=date(2026, 9, 21),
    )

    assert report is not None
    assert report.status == InfoCheckStatus.MISMATCH_FOUND
    model_item = next(
        item
        for item in report.comparisons
        if item.field_name.value == "Models and specifications"
    )
    assert model_item.outcome == CqcWebComparisonOutcome.MISMATCH


def test_verify_expiration_date_fails_when_expired() -> None:
    report = compare_certificate_sources(
        image_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            models_and_specifications="Model A",
            applicable_standards="GB 4706.1",
            valid_until="2020 年 01 月 01 日",
        ),
        website_certificate=CccCertificateFields(
            certificate_number="2025010703748148",
            models_and_specifications="Model A",
            applicable_standards="GB 4706.1",
            certificate_status="有效",
        ),
        website_source_url="https://www.cqc.com.cn/example",
        reference_date=date(2026, 9, 21),
    )

    assert report is not None
    assert report.status == InfoCheckStatus.MISMATCH_FOUND
    expiration = next(
        item
        for item in report.verifications
        if item.check_name == CqcVerificationCheckName.EXPIRATION_DATE
    )
    assert expiration.outcome == CqcWebVerificationOutcome.FAIL


def test_verify_certificate_status_fails_for_invalid_status() -> None:
    report = compare_certificate_sources(
        image_certificate=_matched_fields(),
        website_certificate=_matched_fields().model_copy(
            update={"certificate_status": "暂停"}
        ),
        website_source_url="https://www.cqc.com.cn/example",
        reference_date=date(2026, 9, 21),
    )

    assert report is not None
    assert report.status == InfoCheckStatus.MISMATCH_FOUND
    status_check = next(
        item
        for item in report.verifications
        if item.check_name == CqcVerificationCheckName.CERTIFICATE_STATUS
    )
    assert status_check.outcome == CqcWebVerificationOutcome.FAIL


def test_compare_certificate_sources_skips_without_website_url() -> None:
    report = compare_certificate_sources(
        image_certificate=CccCertificateFields(certificate_number="2025010703748148"),
        website_certificate=None,
        website_source_url=None,
    )

    assert report is None


def test_format_comparison_report_plain_text_includes_comparisons_and_checks() -> None:
    report = compare_certificate_sources(
        image_certificate=_matched_fields(),
        website_certificate=_matched_fields().model_copy(
            update={"certificate_status": "有效"}
        ),
        website_source_url="https://www.cqc.com.cn/example",
        reference_date=date(2026, 9, 21),
    )

    assert report is not None
    text = format_comparison_report_plain_text(report)

    assert "Field comparisons / 字段比对:" in text
    assert "Validity checks / 有效性核验:" in text
    assert "Certificate number: Match" in text
    assert "Expiration date validity: Pass" in text
    assert "Certificate status validity: Pass" in text
    assert "2025010703748148" in text
