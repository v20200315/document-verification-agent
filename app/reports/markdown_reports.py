from __future__ import annotations

from sandbox.app.verify_test_report.backend import ComplianceReport, TestReportResult
from sandbox.src.schemas import CqcWebComparisonReport, ProcessedDocument


def build_ccc_final_markdown(processed: ProcessedDocument) -> str:
    """Render the CCC final verification report as Markdown (no intermediate steps)."""
    lines = [
        "# CCC 证书核验最终报告",
        "",
        "## 基本信息",
        "",
        f"- 文件 MD5：`{processed.file_md5}`",
    ]
    if processed.processing_error:
        lines.extend(
            [
                "",
                "## 解析说明",
                "",
                f"> {processed.processing_error}",
            ]
        )

    comparison = processed.cqc_comparison_report
    if comparison is None:
        lines.extend(
            [
                "",
                "## 比对结论",
                "",
                "> 未识别到 CQC 官网链接，无法生成上传文档与官网的比对报告。",
            ]
        )
        return _finalize_markdown(lines)

    lines.extend(["", _comparison_report_markdown(comparison)])
    return _finalize_markdown(lines)


def build_test_report_final_markdown(
    classification: TestReportResult,
    compliance: ComplianceReport | None,
    validation_note: str | None,
) -> str:
    """Render the test report final verification report as Markdown."""
    lines = [
        "# 检测报告核验最终报告",
        "",
        "## 基本信息",
        "",
        f"- 文件：`{classification.file_name}`",
        f"- 页数：{classification.page_count}",
        f"- 产品类别：{classification.product_category.value}",
    ]
    if classification.category_confidence is not None:
        lines.append(f"- 分类置信度：{classification.category_confidence:.2f}")

    if compliance is None:
        lines.extend(["", "## 核验结论", ""])
        note = validation_note or "未生成合规核验报告。"
        lines.append(f"> {note}")
        return _finalize_markdown(lines)

    status_label = _compliance_status_label(compliance.overall_status.value)
    lines.extend(
        [
            "",
            "## 总体结果",
            "",
            f"- 结论：**{compliance.overall_status.value}**（{status_label}）",
            "",
            "## 摘要",
            "",
            compliance.summary,
            "",
            "## 规则核验",
            "",
        ]
    )
    for finding in compliance.findings:
        finding_status = _compliance_status_label(finding.status.value)
        lines.extend(
            [
                f"### {finding.rule_number}. {finding.rule_text}",
                "",
                f"- 结果：**{finding.status.value}**（{finding_status}）",
                f"- 依据：{finding.evidence}",
                "",
            ]
        )
    return _finalize_markdown(lines)


def _comparison_report_markdown(report: CqcWebComparisonReport) -> str:
    sections: list[str] = [
        "## 总体结果",
        "",
        f"- 结论：**{report.status.value}**",
        "",
        "## 摘要",
        "",
        report.summary,
    ]
    if report.website_source_url:
        sections.extend(["", f"- 官网来源：{report.website_source_url}"])
    if report.website_fetch_error:
        sections.extend(["", f"> 官网抓取错误：{report.website_fetch_error}"])

    sections.extend(["", "## 字段比对", ""])
    for item in report.comparisons:
        sections.extend(
            [
                f"### {item.field_name.value}",
                "",
                f"- 结果：**{item.outcome.value}**",
                f"- 上传文档：{_display(item.image_value)}",
                f"- 官网数据：{_display(item.website_value)}",
                f"- 说明：{item.explanation}",
                "",
            ]
        )

    sections.extend(["## 有效性核验", ""])
    for item in report.verifications:
        sections.extend(
            [
                f"### {item.check_name.value}",
                "",
                f"- 结果：**{item.outcome.value}**",
                f"- 数据来源：{item.source}",
                f"- 观测值：{_display(item.observed_value)}",
                f"- 说明：{item.explanation}",
                "",
            ]
        )

    sections.extend(["## 说明", "", report.limitations])
    return "\n".join(sections)


def _compliance_status_label(status: str) -> str:
    mapping = {
        "Pass": "通过",
        "Fail": "未通过",
        "Insufficient evidence": "证据不足",
    }
    return mapping.get(status, status)


def _display(value: str | None) -> str:
    if value is None or not value.strip():
        return "（空）"
    return value.strip()


def _finalize_markdown(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    return f"{text}\n"
