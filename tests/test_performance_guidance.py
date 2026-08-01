from __future__ import annotations

from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REFERENCE = PRODUCT_ROOT / "skill" / "editaplot" / "references" / "runtime.md"
INSTALLATION_GUIDE = PRODUCT_ROOT / "docs" / "installation.md"


def test_runtime_timing_guidance_separates_normal_triage_from_a_performance_promise() -> None:
    text = RUNTIME_REFERENCE.read_text(encoding="utf-8")

    assert "up to roughly **4–5 minutes** can be treated as normal" in text
    assert "**30–60 minutes** without a pending user question" in text
    assert "not a hardware-independent\nservice-level promise" in text
    assert 'Do not diagnose "slow network" from total time alone.' in text
    assert "Do not promise that every computer will finish inside five minutes" in text


def test_runtime_timing_guidance_keeps_all_five_cost_groups_and_worker_clock_scope() -> None:
    text = RUNTIME_REFERENCE.read_text(encoding="utf-8")

    for heading in (
        "Download and dependencies",
        "Environment diagnosis",
        "Data understanding",
        "Origin startup and connection",
        "Drawing, export, and verification",
    ):
        assert heading in text
    for stage in (
        "`origin_smoke`",
        "`load_template`",
        "`create_output_dir`",
        "`validate_csv`",
        "`analyze_data`",
        "`launch_origin_draw_export_verify`",
        "`verify_outputs`",
    ):
        assert stage in text
    assert "`elapsed_seconds`" in text
    assert "It resets between\nthe smoke worker and the render worker" in text
    assert "it is not the total Codex task duration" in text


def test_chinese_beginner_guide_explains_when_to_stop_and_what_to_report() -> None:
    text = INSTALLATION_GUIDE.read_text(encoding="utf-8")

    assert "完整流程在 **4–5 分钟内**" in text
    assert "**30–60 分钟**都没有新的本地进度，这属于异常" in text
    assert "不能只看到总时间长，\n就直接认定是网络慢" in text
    assert "不要把等待回复算作程序耗时" in text
    assert "`type`、`step` 和 `elapsed_seconds`" in text
    for category in ("下载", "环境", "数据理解", "Origin 连接", "绘图\n导出"):
        assert category in text
