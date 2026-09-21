from __future__ import annotations

import re

from sandbox.src.schemas import (
    CccCertificateFields,
    CertificateFieldName,
    CqcWebComparisonItem,
    CqcWebComparisonOutcome,
    CqcWebComparisonReport,
    InfoCheckStatus,
)

COMPARISON_LIMITATIONS = (
    "本报告仅比较上传文档提取结果与 CQC 官网当前版本映射字段。"
    "两者均依赖模型或页面解析，无法单独作为证书真实性证明。"
)

CERTIFICATE_FIELD_ATTRS: list[tuple[CertificateFieldName, str]] = [
    (CertificateFieldName.CERTIFICATE_NUMBER, "certificate_number"),
    (CertificateFieldName.STATUS, "certificate_status"),
    (CertificateFieldName.HOLDER, "certificate_holder"),
    (CertificateFieldName.MANUFACTURER, "manufacturer"),
    (CertificateFieldName.FACTORY, "production_factory"),
    (CertificateFieldName.PRODUCT, "product_name"),
    (CertificateFieldName.MODEL, "models_and_specifications"),
    (CertificateFieldName.STANDARDS, "applicable_standards"),
    (CertificateFieldName.ISSUING_BODY, "issuing_certification_body"),
    (CertificateFieldName.ISSUE_DATE, "issue_date"),
    (CertificateFieldName.VALID_UNTIL, "valid_until"),
]


def compare_certificate_sources(
    *,
    image_certificate: CccCertificateFields | None,
    website_certificate: CccCertificateFields | None,
    website_source_url: str | None,
    website_fetch_error: str | None = None,
) -> CqcWebComparisonReport | None:
    """Compare uploaded image fields with mapped current-version CQC website fields."""
    if website_source_url is None and website_fetch_error is None:
        return None

    image = image_certificate or CccCertificateFields()
    website = website_certificate or CccCertificateFields()
    comparisons = [
        _compare_field(field_name, attr, image, website)
        for field_name, attr in CERTIFICATE_FIELD_ATTRS
    ]
    status = _derive_status(comparisons)
    return CqcWebComparisonReport(
        status=status,
        comparisons=comparisons,
        summary=_build_summary(status, comparisons, website_fetch_error),
        limitations=COMPARISON_LIMITATIONS,
        website_source_url=website_source_url,
        website_fetch_error=website_fetch_error,
    )


def format_comparison_report_plain_text(report: CqcWebComparisonReport) -> str:
    """Render a comparison report as plain text."""
    lines = [
        f"Status / 状态: {report.status.value}",
        f"Summary / 摘要: {report.summary}",
    ]
    if report.website_source_url:
        lines.append(f"Website URL / 官网链接: {report.website_source_url}")
    if report.website_fetch_error:
        lines.append(f"Website fetch error / 官网抓取错误: {report.website_fetch_error}")
    lines.extend(["", "Field comparisons / 字段比对:"])
    for item in report.comparisons:
        lines.extend(
            [
                f"- {item.field_name.value}: {item.outcome.value}",
                f"  Image / 上传: {_display_value(item.image_value)}",
                f"  Website / 官网: {_display_value(item.website_value)}",
                f"  Note / 说明: {item.explanation}",
            ]
        )
    lines.extend(["", f"Limitations / 说明: {report.limitations}"])
    return "\n".join(lines)


def _compare_field(
    field_name: CertificateFieldName,
    attr: str,
    image: CccCertificateFields,
    website: CccCertificateFields,
) -> CqcWebComparisonItem:
    image_value = _clean_value(getattr(image, attr))
    website_value = _clean_value(getattr(website, attr))

    if not image_value and not website_value:
        return CqcWebComparisonItem(
            field_name=field_name,
            image_value=None,
            website_value=None,
            outcome=CqcWebComparisonOutcome.MATCH,
            explanation="双方均未提供该字段。",
        )
    if not image_value:
        return CqcWebComparisonItem(
            field_name=field_name,
            image_value=None,
            website_value=website_value,
            outcome=CqcWebComparisonOutcome.MISSING_IMAGE,
            explanation="上传文档中缺少该字段，但官网当前版本存在。",
        )
    if not website_value:
        return CqcWebComparisonItem(
            field_name=field_name,
            image_value=image_value,
            website_value=None,
            outcome=CqcWebComparisonOutcome.MISSING_WEBSITE,
            explanation="官网当前版本中缺少该字段，但上传文档存在。",
        )
    if _values_equivalent(image_value, website_value):
        return CqcWebComparisonItem(
            field_name=field_name,
            image_value=image_value,
            website_value=website_value,
            outcome=CqcWebComparisonOutcome.MATCH,
            explanation="字段内容一致。",
        )
    if _one_contains_other(image_value, website_value):
        return CqcWebComparisonItem(
            field_name=field_name,
            image_value=image_value,
            website_value=website_value,
            outcome=CqcWebComparisonOutcome.MATCH,
            explanation="字段内容实质一致，仅存在地址或格式差异。",
        )
    return CqcWebComparisonItem(
        field_name=field_name,
        image_value=image_value,
        website_value=website_value,
        outcome=CqcWebComparisonOutcome.MISMATCH,
        explanation="字段内容不一致。",
    )


def _derive_status(comparisons: list[CqcWebComparisonItem]) -> InfoCheckStatus:
    outcomes = {item.outcome for item in comparisons}
    if CqcWebComparisonOutcome.MISMATCH in outcomes:
        return InfoCheckStatus.MISMATCH_FOUND
    missing_or_inconclusive = {
        CqcWebComparisonOutcome.MISSING_IMAGE,
        CqcWebComparisonOutcome.MISSING_WEBSITE,
        CqcWebComparisonOutcome.INCONCLUSIVE,
    }
    if outcomes.intersection(missing_or_inconclusive):
        return InfoCheckStatus.INCONCLUSIVE
    return InfoCheckStatus.ALL_MATCHED


def _build_summary(
    status: InfoCheckStatus,
    comparisons: list[CqcWebComparisonItem],
    website_fetch_error: str | None,
) -> str:
    match_count = sum(
        1 for item in comparisons if item.outcome == CqcWebComparisonOutcome.MATCH
    )
    mismatch_count = sum(
        1 for item in comparisons if item.outcome == CqcWebComparisonOutcome.MISMATCH
    )
    missing_count = len(comparisons) - match_count - mismatch_count
    if website_fetch_error:
        return (
            f"已完成 {len(comparisons)} 项字段比对；"
            f"一致 {match_count} 项，不一致 {mismatch_count} 项，"
            f"缺失或不可比 {missing_count} 项。"
            f"官网抓取存在问题：{website_fetch_error}"
        )
    if status == InfoCheckStatus.ALL_MATCHED:
        return f"已完成 {len(comparisons)} 项字段比对，全部一致。"
    if status == InfoCheckStatus.MISMATCH_FOUND:
        return (
            f"已完成 {len(comparisons)} 项字段比对，"
            f"发现 {mismatch_count} 项不一致。"
        )
    return (
        f"已完成 {len(comparisons)} 项字段比对；"
        f"一致 {match_count} 项，不一致 {mismatch_count} 项，"
        f"缺失或不可比 {missing_count} 项。"
    )


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_value(value: str) -> str:
    text = value.strip()
    text = re.sub(r"\s+", "", text)
    text = text.replace("；", ";").replace("，", ",").replace("～", "~")
    text = text.replace("—", "-").replace("–", "-")
    return text.casefold()


def _values_equivalent(left: str, right: str) -> bool:
    return _normalize_value(left) == _normalize_value(right)


def _one_contains_other(left: str, right: str) -> bool:
    left_norm = _normalize_value(left)
    right_norm = _normalize_value(right)
    if len(left_norm) < 8 or len(right_norm) < 8:
        return False
    return left_norm in right_norm or right_norm in left_norm


def _display_value(value: str | None) -> str:
    return value if value else "(empty)"
