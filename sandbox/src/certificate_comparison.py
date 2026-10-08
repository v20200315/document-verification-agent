from __future__ import annotations

import re
from datetime import UTC, date, datetime

from sandbox.src.schemas import (
    CccCertificateFields,
    CertificateFieldName,
    CqcVerificationCheckName,
    CqcWebComparisonItem,
    CqcWebComparisonOutcome,
    CqcWebComparisonReport,
    CqcWebVerificationItem,
    CqcWebVerificationOutcome,
    InfoCheckStatus,
)

COMPARISON_LIMITATIONS = (
    "本报告仅比较上传文档与 CQC 官网当前版本映射字段中的证书编号、型号规格、"
    "适用标准，并分别依据上传文档有效期与官网证书状态进行有效性核验。"
    "两者均依赖模型或页面解析，无法单独作为证书真实性证明。"
)

COMPARISON_FIELD_ATTRS: list[tuple[CertificateFieldName, str]] = [
    (CertificateFieldName.CERTIFICATE_NUMBER, "certificate_number"),
    (CertificateFieldName.MODEL, "models_and_specifications"),
    (CertificateFieldName.STANDARDS, "applicable_standards"),
]

CHINESE_DATE_PATTERN = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
ISO_DATE_PATTERN = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")

VALID_STATUS_TOKENS = ("有效", "valid", "正常")
INVALID_STATUS_TOKENS = (
    "暂停",
    "撤销",
    "注销",
    "过期",
    "失效",
    "无效",
    "suspended",
    "revoked",
    "cancelled",
    "canceled",
    "expired",
    "invalid",
)


def compare_certificate_sources(
    *,
    image_certificate: CccCertificateFields | None,
    website_certificate: CccCertificateFields | None,
    website_source_url: str | None,
    website_fetch_error: str | None = None,
    reference_date: date | None = None,
) -> CqcWebComparisonReport | None:
    """Compare uploaded image fields with mapped current-version CQC website fields."""
    if website_source_url is None and website_fetch_error is None:
        return None

    image = image_certificate or CccCertificateFields()
    website = website_certificate or CccCertificateFields()
    today = reference_date or datetime.now(UTC).date()
    comparisons = [
        _compare_field(field_name, attr, image, website)
        for field_name, attr in COMPARISON_FIELD_ATTRS
    ]
    verifications = [
        _verify_expiration_date(image.valid_until, today),
        _verify_certificate_status(website.certificate_status),
    ]
    status = _derive_status(comparisons, verifications)
    return CqcWebComparisonReport(
        status=status,
        comparisons=comparisons,
        verifications=verifications,
        summary=_build_summary(status, comparisons, verifications, website_fetch_error),
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
    lines.extend(["", "Validity checks / 有效性核验:"])
    for item in report.verifications:
        lines.extend(
            [
                f"- {item.check_name.value}: {item.outcome.value}",
                f"  Source / 来源: {item.source}",
                f"  Observed / 观测值: {_display_value(item.observed_value)}",
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
            explanation="字段内容实质一致，仅存在格式差异。",
        )
    return CqcWebComparisonItem(
        field_name=field_name,
        image_value=image_value,
        website_value=website_value,
        outcome=CqcWebComparisonOutcome.MISMATCH,
        explanation="字段内容不一致。",
    )


def _verify_expiration_date(
    valid_until: str | None,
    reference_date: date,
) -> CqcWebVerificationItem:
    cleaned = _clean_value(valid_until)
    if cleaned is None:
        return CqcWebVerificationItem(
            check_name=CqcVerificationCheckName.EXPIRATION_DATE,
            source="uploaded document",
            observed_value=None,
            outcome=CqcWebVerificationOutcome.INCONCLUSIVE,
            explanation="上传文档未提供有效期至，无法核验是否过期。",
        )

    parsed = _parse_certificate_date(cleaned)
    if parsed is None:
        return CqcWebVerificationItem(
            check_name=CqcVerificationCheckName.EXPIRATION_DATE,
            source="uploaded document",
            observed_value=cleaned,
            outcome=CqcWebVerificationOutcome.INCONCLUSIVE,
            explanation="上传文档中的有效期格式无法识别，无法核验是否过期。",
        )
    if reference_date <= parsed:
        return CqcWebVerificationItem(
            check_name=CqcVerificationCheckName.EXPIRATION_DATE,
            source="uploaded document",
            observed_value=cleaned,
            outcome=CqcWebVerificationOutcome.PASS,
            explanation=(
                f"依据上传文档，证书有效期至 {parsed.isoformat()}，"
                f"在参考日期 {reference_date.isoformat()} 仍未过期。"
            ),
        )
    return CqcWebVerificationItem(
        check_name=CqcVerificationCheckName.EXPIRATION_DATE,
        source="uploaded document",
        observed_value=cleaned,
        outcome=CqcWebVerificationOutcome.FAIL,
        explanation=(
            f"依据上传文档，证书有效期至 {parsed.isoformat()}，"
            f"在参考日期 {reference_date.isoformat()} 已过期。"
        ),
    )


def _verify_certificate_status(status: str | None) -> CqcWebVerificationItem:
    cleaned = _clean_value(status)
    if cleaned is None:
        return CqcWebVerificationItem(
            check_name=CqcVerificationCheckName.CERTIFICATE_STATUS,
            source="CQC website",
            observed_value=None,
            outcome=CqcWebVerificationOutcome.INCONCLUSIVE,
            explanation="官网当前版本未提供证书状态，无法核验是否有效。",
        )

    normalized = _normalize_value(cleaned)
    if any(token in normalized for token in _normalized_tokens(INVALID_STATUS_TOKENS)):
        return CqcWebVerificationItem(
            check_name=CqcVerificationCheckName.CERTIFICATE_STATUS,
            source="CQC website",
            observed_value=cleaned,
            outcome=CqcWebVerificationOutcome.FAIL,
            explanation="依据官网当前版本，证书状态显示为非有效状态。",
        )
    if any(token in normalized for token in _normalized_tokens(VALID_STATUS_TOKENS)):
        return CqcWebVerificationItem(
            check_name=CqcVerificationCheckName.CERTIFICATE_STATUS,
            source="CQC website",
            observed_value=cleaned,
            outcome=CqcWebVerificationOutcome.PASS,
            explanation="依据官网当前版本，证书状态为有效。",
        )
    return CqcWebVerificationItem(
        check_name=CqcVerificationCheckName.CERTIFICATE_STATUS,
        source="CQC website",
        observed_value=cleaned,
        outcome=CqcWebVerificationOutcome.INCONCLUSIVE,
        explanation="官网证书状态无法明确判定为有效或非有效。",
    )


def _derive_status(
    comparisons: list[CqcWebComparisonItem],
    verifications: list[CqcWebVerificationItem],
) -> InfoCheckStatus:
    comparison_outcomes = {item.outcome for item in comparisons}
    verification_outcomes = {item.outcome for item in verifications}

    if (
        CqcWebComparisonOutcome.MISMATCH in comparison_outcomes
        or CqcWebVerificationOutcome.FAIL in verification_outcomes
    ):
        return InfoCheckStatus.MISMATCH_FOUND

    inconclusive = {
        CqcWebComparisonOutcome.MISSING_IMAGE,
        CqcWebComparisonOutcome.MISSING_WEBSITE,
        CqcWebComparisonOutcome.INCONCLUSIVE,
        CqcWebVerificationOutcome.INCONCLUSIVE,
    }
    if comparison_outcomes.intersection(inconclusive) or (
        CqcWebVerificationOutcome.INCONCLUSIVE in verification_outcomes
    ):
        return InfoCheckStatus.INCONCLUSIVE

    return InfoCheckStatus.ALL_MATCHED


def _build_summary(
    status: InfoCheckStatus,
    comparisons: list[CqcWebComparisonItem],
    verifications: list[CqcWebVerificationItem],
    website_fetch_error: str | None,
) -> str:
    match_count = sum(
        1 for item in comparisons if item.outcome == CqcWebComparisonOutcome.MATCH
    )
    mismatch_count = sum(
        1 for item in comparisons if item.outcome == CqcWebComparisonOutcome.MISMATCH
    )
    missing_count = len(comparisons) - match_count - mismatch_count
    pass_count = sum(
        1 for item in verifications if item.outcome == CqcWebVerificationOutcome.PASS
    )
    fail_count = sum(
        1 for item in verifications if item.outcome == CqcWebVerificationOutcome.FAIL
    )
    inconclusive_count = len(verifications) - pass_count - fail_count

    parts = [
        (
            f"已完成 {len(comparisons)} 项字段比对（一致 {match_count} 项，"
            f"不一致 {mismatch_count} 项，缺失或不可比 {missing_count} 项），"
            f"以及 {len(verifications)} 项有效性核验（通过 {pass_count} 项，"
            f"未通过 {fail_count} 项，不确定 {inconclusive_count} 项）。"
        ),
    ]
    if website_fetch_error:
        parts.append(f"官网抓取存在问题：{website_fetch_error}")
    elif status == InfoCheckStatus.ALL_MATCHED:
        parts.append("全部字段一致且有效性核验通过。")
    elif status == InfoCheckStatus.MISMATCH_FOUND:
        parts.append("发现字段不一致或有效性核验未通过。")
    else:
        parts.append("存在缺失字段或无法完成的有效性核验。")
    return "".join(parts)


def _parse_certificate_date(value: str) -> date | None:
    for pattern in (CHINESE_DATE_PATTERN, ISO_DATE_PATTERN):
        match = pattern.search(value)
        if not match:
            continue
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def _normalized_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_normalize_value(token) for token in tokens)


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
