from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

from sandbox.app.verify_test_report.backend import (
    CLASSIFICATION_FALLBACK_PREFIX,
    DEFAULT_RULES_DIR,
    IMAGE_ONLY_MESSAGE,
    RULE_FILES,
    ComplianceStatus,
    ProductCategory,
    RuleFinding,
    TestReportAnalyzer,
    TestReportClassifier,
    TestReportError,
    TestReportResult,
    TestReportValidator,
    TextReportLoader,
    aggregate_compliance_status,
    build_classification_prompt,
    load_category_rules,
    parse_top_level_rules,
)
from sandbox.app.verify_test_report.service import (
    MAX_UPLOAD_BYTES,
    classify_uploaded_pdf,
    validate_classified_report,
)


class SequenceModel:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[Any] = []

    def invoke(self, value: Any) -> Any:
        self.calls.append(value)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class StructuredFactory:
    def __init__(self, structured_model: SequenceModel) -> None:
        self.structured_model = structured_model
        self.options: dict[str, Any] = {}

    def with_structured_output(self, _schema: Any, **kwargs: Any) -> Any:
        self.options = kwargs
        return self.structured_model


def _write_text_pdf(path: Path, pages: list[str]) -> None:
    canvas = Canvas(str(path))
    for text in pages:
        canvas.drawString(72, 720, text)
        canvas.showPage()
    canvas.save()


def test_text_pdf_pages_are_extracted_in_order(tmp_path: Path) -> None:
    pdf_path = tmp_path / "report.pdf"
    _write_text_pdf(pdf_path, ["Heat pump page one.", "Boiler page two."])

    full_content, page_count = TextReportLoader().load(pdf_path)

    assert page_count == 2
    assert "--- Page 1 ---\nHeat pump page one." in full_content
    assert "--- Page 2 ---\nBoiler page two." in full_content


def test_image_only_pdf_is_rejected(tmp_path: Path) -> None:
    pdf_path = tmp_path / "image-only.pdf"
    Image.new("RGB", (40, 40), "white").save(pdf_path)

    with pytest.raises(TestReportError, match="No selectable text"):
        TextReportLoader().load(pdf_path)
    assert "Image PDF to Text PDF" in IMAGE_ONLY_MESSAGE


def test_password_protected_pdf_is_rejected(tmp_path: Path) -> None:
    source_path = tmp_path / "open.pdf"
    _write_text_pdf(source_path, ["Selectable text."])
    locked_path = tmp_path / "locked.pdf"
    writer = PdfWriter()
    writer.append(str(source_path))
    writer.encrypt("secret")
    writer.write(str(locked_path))

    with pytest.raises(TestReportError, match="password-protected"):
        TextReportLoader().load(locked_path)


@pytest.mark.parametrize(
    ("category", "reasoning"),
    [
        (ProductCategory.HEAT_FAN, "报告名称含热风机。"),
        (ProductCategory.HEAT_PUMP_CHILLER, "报告覆盖冷水机组工况。"),
        (ProductCategory.STORAGE_HEATER, "样品为蓄热式电暖器。"),
        (ProductCategory.GAS_BOILER, "铭牌标明燃气壁挂炉。"),
        (ProductCategory.OTHER, "文本无法对应四类产品。"),
    ],
)
def test_classifier_accepts_each_closed_category(
    category: ProductCategory,
    reasoning: str,
) -> None:
    structured = SequenceModel(
        [
            {
                "parsed": {
                    "product_category": category.value,
                    "category_confidence": 0.91,
                    "category_reasoning": reasoning,
                },
                "parsing_error": None,
            }
        ]
    )
    factory = StructuredFactory(structured)

    result = TestReportClassifier(factory, max_attempts=1).classify("检测报告正文")

    assert result.product_category is category
    assert result.category_confidence == 0.91
    assert result.category_reasoning == reasoning
    assert factory.options["method"] == "json_schema"
    assert factory.options["strict"] is True


def test_classifier_retries_malformed_structured_output() -> None:
    structured = SequenceModel(
        [
            {"parsed": None, "parsing_error": ValueError("bad JSON")},
            {
                "parsed": {
                    "product_category": ProductCategory.STORAGE_HEATER.value,
                    "category_confidence": 0.8,
                    "category_reasoning": "样品名称写明蓄热式电暖器。",
                },
                "parsing_error": None,
            },
        ]
    )

    result = TestReportClassifier(
        StructuredFactory(structured),
        max_attempts=2,
    ).classify("蓄热式电暖器检测报告")

    assert result.product_category is ProductCategory.STORAGE_HEATER
    assert len(structured.calls) == 2


def test_classifier_falls_back_to_other_after_retries() -> None:
    structured = SequenceModel(
        [
            {"parsed": None, "parsing_error": ValueError("bad JSON")},
            {"parsed": None, "parsing_error": ValueError("still bad")},
        ]
    )

    result = TestReportClassifier(
        StructuredFactory(structured),
        max_attempts=2,
    ).classify("unknown report")

    assert result.product_category is ProductCategory.OTHER
    assert result.category_confidence is None
    assert result.category_reasoning.startswith(CLASSIFICATION_FALLBACK_PREFIX)


def test_analyzer_returns_extracted_text_and_classification(tmp_path: Path) -> None:
    pdf_path = tmp_path / "heater.pdf"
    _write_text_pdf(pdf_path, ["Storage heater type test report."])
    structured = SequenceModel(
        [
            {
                "parsed": {
                    "product_category": ProductCategory.STORAGE_HEATER.value,
                    "category_confidence": 0.88,
                    "category_reasoning": "封面写明蓄热式电暖器。",
                },
                "parsing_error": None,
            }
        ]
    )
    analyzer = TestReportAnalyzer(
        loader=TextReportLoader(),
        classifier=TestReportClassifier(StructuredFactory(structured), max_attempts=1),
    )

    result = analyzer.analyze(pdf_path)

    assert result.file_name == "heater.pdf"
    assert result.page_count == 1
    assert result.product_category is ProductCategory.STORAGE_HEATER
    assert "Storage heater type test report." in result.full_content


def test_upload_service_rejects_empty_and_oversized_pdfs() -> None:
    class UnusedAnalyzer:
        def analyze(self, path: str | Path) -> TestReportResult:
            raise AssertionError(f"should not analyze {path}")

    with pytest.raises(TestReportError, match="empty"):
        classify_uploaded_pdf("empty.pdf", b"", analyzer_factory=UnusedAnalyzer)
    with pytest.raises(TestReportError, match="50 MB"):
        classify_uploaded_pdf(
            "huge.pdf",
            b"x" * (MAX_UPLOAD_BYTES + 1),
            analyzer_factory=UnusedAnalyzer,
        )


def test_upload_service_removes_temporary_pdf() -> None:
    observed_paths: list[Path] = []
    expected = TestReportResult(
        file_name="report.pdf",
        page_count=1,
        product_category=ProductCategory.OTHER,
        category_reasoning="无法归入四类产品。",
        full_content="--- Page 1 ---\nUnrelated report.",
    )

    class FakeAnalyzer:
        def analyze(self, path: str | Path) -> TestReportResult:
            temporary_path = Path(path)
            observed_paths.append(temporary_path)
            assert temporary_path.is_file()
            return expected

    result = classify_uploaded_pdf(
        "report.pdf",
        b"%PDF-upload",
        analyzer_factory=FakeAnalyzer,
    )

    assert result is expected
    assert observed_paths
    assert all(not path.exists() for path in observed_paths)


def _sample_rules() -> dict[ProductCategory, str]:
    return {
        ProductCategory.HEAT_FAN: "RULE_HEAT_FAN_UNIQUE",
        ProductCategory.HEAT_PUMP_CHILLER: "RULE_CHILLER_UNIQUE",
        ProductCategory.STORAGE_HEATER: "RULE_HEATER_UNIQUE",
        ProductCategory.GAS_BOILER: "RULE_BOILER_UNIQUE",
    }


def test_default_category_rule_files_cover_every_product_except_other() -> None:
    rules = load_category_rules()

    assert set(rules) == set(RULE_FILES)
    assert ProductCategory.OTHER not in rules
    assert not (DEFAULT_RULES_DIR / "other.md").exists()
    for category, file_name in RULE_FILES.items():
        assert (DEFAULT_RULES_DIR / file_name).is_file()
        assert category.value in rules[category]


def test_missing_category_rule_file_is_rejected(tmp_path: Path) -> None:
    for file_name in RULE_FILES.values():
        (tmp_path / file_name).write_text("rule", encoding="utf-8")
    (tmp_path / RULE_FILES[ProductCategory.GAS_BOILER]).unlink()

    with pytest.raises(TestReportError, match="gas_boiler.md"):
        load_category_rules(tmp_path)


def test_classification_prompt_includes_loaded_rules() -> None:
    prompt = build_classification_prompt(_sample_rules())

    assert "RULE_HEAT_FAN_UNIQUE" in prompt
    assert "RULE_CHILLER_UNIQUE" in prompt
    assert "RULE_HEATER_UNIQUE" in prompt
    assert "RULE_BOILER_UNIQUE" in prompt
    assert "<category_rules>" in prompt
    assert ProductCategory.OTHER.value in prompt


def test_classifier_sends_loaded_rules_to_the_model() -> None:
    structured = SequenceModel(
        [
            {
                "parsed": {
                    "product_category": ProductCategory.GAS_BOILER.value,
                    "category_confidence": 0.7,
                    "category_reasoning": "符合燃气壁挂炉规则。",
                },
                "parsing_error": None,
            }
        ]
    )

    TestReportClassifier(
        StructuredFactory(structured),
        max_attempts=1,
        category_rules=_sample_rules(),
    ).classify("检测报告正文")

    system_message = structured.calls[0][0]
    assert "RULE_BOILER_UNIQUE" in system_message.content
    assert "RULE_HEAT_FAN_UNIQUE" in system_message.content


def test_non_pdf_upload_name_is_rejected() -> None:
    class UnusedAnalyzer:
        def analyze(self, path: str | Path) -> TestReportResult:
            raise AssertionError(f"should not analyze {path}")

    with pytest.raises(TestReportError, match=".pdf"):
        classify_uploaded_pdf(
            "report.txt",
            b"not a pdf",
            analyzer_factory=UnusedAnalyzer,
        )


TWO_RULES = """# 燃气壁挂炉

1. 应具备 CCC 认证证书。
2. 应免费保修不低于 5 年。
"""


def _classified_result(**overrides: Any) -> TestReportResult:
    values: dict[str, Any] = {
        "file_name": "report.pdf",
        "page_count": 1,
        "product_category": ProductCategory.GAS_BOILER,
        "category_reasoning": "铭牌标明燃气壁挂炉。",
        "full_content": "--- Page 1 ---\n燃气壁挂炉检测报告，具备 CCC 认证。",
    }
    values.update(overrides)
    return TestReportResult(**values)


def _finding_payloads(statuses: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "rule_number": index,
            "status": status,
            "evidence": f"规则 {index} 的核验说明。",
        }
        for index, status in enumerate(statuses, start=1)
    ]


def test_parser_keeps_only_top_level_numbered_rules() -> None:
    markdown = (DEFAULT_RULES_DIR / "heat_fan.md").read_text(encoding="utf-8")
    rules = parse_top_level_rules(markdown)

    assert [rule.number for rule in rules] == [1, 2, 3, 4, 5, 6, 7]
    assert "检验报告涵盖：" in rules[2].text
    assert "COP" not in rules[2].text


def test_other_category_cannot_be_validated() -> None:
    class UnusedModel:
        def with_structured_output(self, _schema: Any, **_kwargs: Any) -> Any:
            return self

        def invoke(self, _messages: Any) -> Any:
            raise AssertionError("Other must be rejected before the model is called")

        def validate(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("Other must be rejected before the validator runs")

    with pytest.raises(TestReportError, match="Other"):
        TestReportValidator(UnusedModel(), max_attempts=1).validate(
            ProductCategory.OTHER,
            "unrelated",
            TWO_RULES,
        )
    with pytest.raises(TestReportError, match="Other"):
        validate_classified_report(
            _classified_result(
                product_category=ProductCategory.OTHER,
                category_reasoning="无法归入四类产品。",
            ),
            validator_factory=UnusedModel,
        )


def test_validator_sends_only_classified_category_rules(tmp_path: Path) -> None:
    for category, file_name in RULE_FILES.items():
        (tmp_path / file_name).write_text(
            f"# {category.value}\n\n1. Unique {file_name} requirement.\n",
            encoding="utf-8",
        )
    structured = SequenceModel(
        [
            {
                "parsed": {
                    "summary": "仅核验燃气壁挂炉规则。",
                    "findings": _finding_payloads(["Pass"]),
                },
                "parsing_error": None,
            }
        ]
    )

    report = validate_classified_report(
        _classified_result(),
        validator_factory=lambda: TestReportValidator(
            StructuredFactory(structured),
            max_attempts=1,
        ),
        rules_dir=tmp_path,
    )

    user_message = structured.calls[0][1].content
    assert report.product_category is ProductCategory.GAS_BOILER
    assert "Unique gas_boiler.md requirement." in user_message
    assert "Unique heat_fan.md requirement." not in user_message
    assert "低环境温度空气源热泵热风机" not in user_message


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["Pass", "Pass"], ComplianceStatus.PASS),
        (["Pass", "Insufficient evidence"], ComplianceStatus.INSUFFICIENT),
        (["Fail", "Insufficient evidence"], ComplianceStatus.FAIL),
        (["Pass", "Fail"], ComplianceStatus.FAIL),
    ],
)
def test_overall_status_aggregates_findings(
    statuses: list[str],
    expected: ComplianceStatus,
) -> None:
    findings = [
        RuleFinding(
            rule_number=index,
            rule_text=f"规则 {index}",
            status=ComplianceStatus(status),
            evidence="说明",
        )
        for index, status in enumerate(statuses, start=1)
    ]
    assert aggregate_compliance_status(findings) is expected

    structured = SequenceModel(
        [
            {
                "parsed": {
                    "summary": "按规则汇总。",
                    "findings": _finding_payloads(statuses),
                },
                "parsing_error": None,
            }
        ]
    )
    report = TestReportValidator(
        StructuredFactory(structured),
        max_attempts=1,
    ).validate(ProductCategory.GAS_BOILER, "报告正文", TWO_RULES)
    assert report.overall_status is expected
    assert [finding.rule_text for finding in report.findings] == [
        "应具备 CCC 认证证书。",
        "应免费保修不低于 5 年。",
    ]


def test_validator_retries_wrong_finding_count_then_errors() -> None:
    structured = SequenceModel(
        [
            {
                "parsed": {
                    "summary": "缺项。",
                    "findings": _finding_payloads(["Pass"]),
                },
                "parsing_error": None,
            },
            {
                "parsed": {
                    "summary": "两项均已核验。",
                    "findings": _finding_payloads(["Pass", "Pass"]),
                },
                "parsing_error": None,
            },
        ]
    )

    report = TestReportValidator(
        StructuredFactory(structured),
        max_attempts=2,
    ).validate(ProductCategory.GAS_BOILER, "报告正文", TWO_RULES)

    assert report.overall_status is ComplianceStatus.PASS
    assert len(structured.calls) == 2

    failing = SequenceModel(
        [
            {
                "parsed": {
                    "summary": "缺项。",
                    "findings": _finding_payloads(["Pass"]),
                },
                "parsing_error": None,
            },
            {
                "parsed": {
                    "summary": "仍然缺项。",
                    "findings": _finding_payloads(["Pass"]),
                },
                "parsing_error": None,
            },
        ]
    )
    with pytest.raises(TestReportError, match="unavailable after retries"):
        TestReportValidator(
            StructuredFactory(failing),
            max_attempts=2,
        ).validate(ProductCategory.GAS_BOILER, "报告正文", TWO_RULES)
