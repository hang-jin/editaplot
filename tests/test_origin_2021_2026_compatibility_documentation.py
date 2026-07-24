from __future__ import annotations

from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = PRODUCT_ROOT / "docs" / "origin-2021-2026-compatibility.md"


def _content() -> str:
    return DOCUMENT.read_text(encoding="utf-8")


def test_document_has_a_complete_official_product_number_table() -> None:
    content = _content()
    expected_rows = {
        "Origin 2021": "9.80",
        "Origin 2021b": "9.85",
        "Origin 2022": "9.90",
        "Origin 2022b": "9.95",
        "Origin 2023": "10.00",
        "Origin 2023b": "10.05",
        "Origin 2024": "10.10",
        "Origin 2024b": "10.15",
        "Origin 2025": "10.20",
        "Origin 2025b": "10.25",
        "Origin 2026": "10.30",
        "Origin 2026b": "10.35",
    }

    for product, number in expected_rows.items():
        assert f"| {product} | {number} |" in content or (
            f"| **{product}** | **{number}** |" in content
        )


def test_document_separates_target_range_from_real_machine_baseline() -> None:
    compact = " ".join(_content().split())

    assert "目标范围是 Windows 上的 Origin / OriginPro 2021 至 2026b" in compact
    assert "2024b（产品号 10.15）是当前唯一完成全链路实机验证的基线" in compact
    assert "进入目标范围”不等于“所有模板已经在该版本逐一验证" in compact
    assert "不能笼统写成“全部已经验证”" in compact


def test_document_states_external_python_and_isolated_instance_boundaries() -> None:
    compact = " ".join(_content().split())

    assert "外部 `originpro` 路线仅适用于 Windows" in compact
    assert "本机需要安装 Origin 2021 或更高版本" in compact
    assert "默认采用隔离实例策略" in compact
    assert "不需要先打开 Origin" in compact
    assert "`Application` 总是创建新实例" in compact
    assert "`attach_existing`" in compact


def test_document_requires_probe_and_real_output_evidence() -> None:
    content = _content()
    compact = " ".join(content.split())

    for evidence in (
        "Automation 握手",
        "版本风险优先级",
        "模板能力探针",
        "OPJU",
        "PNG、PDF、TIF",
        "对象与视觉证据",
        "人工视觉检查",
    ):
        assert evidence in content
    assert "风险记录不会仅凭版本号自动阻断绘图" in compact
    assert "`version_status=unknown`" in content
    assert "完整、高优先级能力探针" in compact
    assert "不会把未知环境静默写成“已支持”或 “已验证”" in compact


def test_document_scopes_public_github_research_without_overclaiming() -> None:
    content = _content()
    compact = " ".join(content.split())

    assert "https://github.com/originlab/Python-Samples" in content
    assert "示例仓库不是一个替代实机验证的通用跨版本兼容层" in compact
    assert "本轮没有找到能够跳过握手、模板能力探针和 真实产物验证" in compact
    assert "并不声称 互联网上绝对不存在其他实验项目" in compact


def test_document_links_the_relevant_official_technical_sources() -> None:
    content = _content()
    expected = (
        "https://docs.originlab.com/externalpython/",
        (
            "https://docs.originlab.com/com/"
            "difference-of-application-applicationsi-and-applicationcomsi/"
        ),
        "https://www.originlab.com/index.aspx?pid=3325",
        "https://docs.originlab.com/quick-help/why-graph-looks-different-in-2025b/",
    )

    assert all(url in content for url in expected)


def test_document_contains_only_technical_compatibility_information() -> None:
    folded = _content().casefold()
    forbidden = (
        "授权",
        "许可",
        "license",
        "licensing",
        "姓名",
        "邮箱",
        "手机号",
        "用户身份",
        "stargazer",
    )

    assert "这里只判断技术可调用性" in folded
    assert all(token.casefold() not in folded for token in forbidden)


def test_document_has_clean_commonmark_structure() -> None:
    lines = _content().splitlines()

    assert lines[0] == "# EditaPlot 的 Origin 2021–2026b 兼容说明"
    assert sum(line.startswith("# ") for line in lines) == 1
    assert all(line == line.rstrip() for line in lines)
    assert "\t" not in "\n".join(lines)
    for index, line in enumerate(lines[:-1]):
        if line.startswith("#"):
            assert lines[index + 1] == ""
