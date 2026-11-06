from runtime.browser.flow import FlowResult, StepFailure, StepResult
from runtime.browser.memory import load_memory, matching_notes, record_failure


def _result(message: str) -> FlowResult:
    return FlowResult(
        flow="b2d-send",
        env="dev",
        result="fail",
        started_at="2026-11-05T10:00:00+08:00",
        duration_ms=100,
        flow_file="flows/b2d-send.yaml",
        steps=[StepResult("打开物流方式", "fail", 100, message)],
        failure=StepFailure(1, "打开物流方式", message, "唯一元素", "命中 2 个"),
    )


def test_failure_is_remembered_and_retrieved_by_control(tmp_path):
    record_failure(tmp_path, _result("el-select 命中 2 个"), control="物流方式", page="/wms/outbound")

    notes = load_memory(tmp_path)

    assert len(notes) == 1
    assert notes[0].control == "物流方式"
    assert notes[0].seen == 1
    found = matching_notes(tmp_path, "修改物流方式")
    assert [note.control for note in found] == ["物流方式"]
    assert matching_notes(tmp_path, "拣货单") == []


def test_same_failure_accumulates_instead_of_duplicating(tmp_path):
    first = record_failure(tmp_path, _result("el-select 命中 2 个"), control="物流方式")
    second = record_failure(tmp_path, _result("el-select 命中 2 个"), control="物流方式")

    notes = load_memory(tmp_path)

    assert len(notes) == 1
    assert second.id == first.id
    assert notes[0].seen == 2


def test_memory_survives_for_the_next_project_run(tmp_path):
    record_failure(tmp_path, _result("浮层未关闭"), control="日期", page="/wms/check")

    notes = load_memory(tmp_path)

    assert notes[0].page == "/wms/check"
    assert "浮层未关闭" in notes[0].symptom
