import pandas as pd

from app.agent.loop import LLMReply, ToolCall, run_agent
from app.agent.tools import MemoryStore, Toolbox, ToolResult
from app.rag.index import build_index
from tests.test_detect import weekly_series


def make_toolbox():
    s = weekly_series()
    s[s.index[70]] += 400
    store = MemoryStore(series={("유동인구", "서귀포시 성산읍"): s, ("버스", "서귀포시 성산읍"): weekly_series(seed=5)})
    idx = build_index([{"doc_id": "api_583", "title": "유동인구 API", "locator": "허브 583", "text": "visitPop 방문자수 시간대별 합"}])
    return Toolbox(store, idx), s.index[70]


class ScriptedLLM:
    """미리 정한 응답을 순서대로 돌려주는 가짜 LLM. 받은 메시지를 기록한다."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def step(self, messages, tools):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def test_tool_calls_run_in_order_and_results_get_ids():
    tb, day = make_toolbox()
    llm = ScriptedLLM([
        LLMReply(tool_calls=[ToolCall("c1", "detect_anomalies", {"signal": "유동인구", "emd": "서귀포시 성산읍"})]),
        LLMReply(tool_calls=[ToolCall("c2", "find_co_movements", {"date": str(day.date()), "emd": "서귀포시 성산읍"})]),
        LLMReply(text="성산읍 방문인구가 평소보다 늘었습니다 [R1]."),
    ])
    run = run_agent("성산읍 이상 신호?", llm, tb)
    assert [c.name for c in run.calls] == ["detect_anomalies", "find_co_movements"]
    assert list(run.results) == ["R1", "R2"]
    r1 = run.results["R1"]
    assert isinstance(r1, ToolResult) and r1.data["anomalies"][0]["date"] == str(day.date())
    assert r1.sources and run.final_text.endswith("[R1].") and not run.stopped


def test_unknown_tool_error_is_returned_to_llm_and_loop_recovers():
    tb, _ = make_toolbox()
    llm = ScriptedLLM([
        LLMReply(tool_calls=[ToolCall("c1", "no_such_tool", {})]),
        LLMReply(text="다시 시도 후 답변"),
    ])
    run = run_agent("질문", llm, tb)
    last_msgs = llm.seen[-1]
    assert any(m.get("role") == "tool" and "unknown tool" in m["content"] for m in last_msgs)
    assert run.final_text == "다시 시도 후 답변" and run.results == {}


def test_bad_arguments_become_tool_error_not_crash():
    tb, _ = make_toolbox()
    llm = ScriptedLLM([
        LLMReply(tool_calls=[ToolCall("c1", "get_series", {"signal": "없는신호", "emd": "서귀포시 성산읍"})]),
        LLMReply(text="데이터가 없습니다"),
    ])
    run = run_agent("질문", llm, tb)
    assert any(m.get("role") == "tool" and "error" in m["content"] for m in llm.seen[-1])
    assert run.final_text == "데이터가 없습니다"


def test_max_steps_stops_loop():
    tb, _ = make_toolbox()
    loop_reply = LLMReply(tool_calls=[ToolCall("c", "search_docs", {"query": "visitPop"})])
    llm = ScriptedLLM([loop_reply] * 10)
    run = run_agent("질문", llm, tb, max_steps=3)
    assert run.stopped and len(run.calls) == 3


def test_tool_specs_cover_all_dispatchable_tools():
    tb, _ = make_toolbox()
    names = {t["name"] for t in tb.specs()}
    assert names == {"get_series", "detect_anomalies", "find_co_movements", "check_context", "search_docs"}


def test_failed_verification_is_sent_back_and_revised():
    tb, day = make_toolbox()
    llm = ScriptedLLM([
        LLMReply(tool_calls=[ToolCall("c1", "detect_anomalies", {"signal": "유동인구", "emd": "서귀포시 성산읍"})]),
        LLMReply(text="방문인구가 99999명이었습니다 [R1]."),           # 틀린 숫자
        LLMReply(text="성산읍에서 이상 신호 1건이 확인됐습니다 [R1]."),  # 수정본
    ])
    run = run_agent("질문", llm, tb)
    assert run.verified and run.revisions == 1
    assert any("검증" in m["content"] for m in llm.seen[-1] if m["role"] == "user")
    assert run.final_text.startswith("성산읍")


def test_unfixable_answer_is_withheld():
    tb, _ = make_toolbox()
    bad = LLMReply(text="방문인구가 99999명이었습니다 [R1].")
    llm = ScriptedLLM([
        LLMReply(tool_calls=[ToolCall("c1", "detect_anomalies", {"signal": "유동인구", "emd": "서귀포시 성산읍"})]),
        bad, bad, bad,
    ])
    run = run_agent("질문", llm, tb, max_revisions=2)
    assert not run.verified and run.revisions == 2
    assert "검증을 통과하지 못해" in run.final_text and "99999" not in run.final_text


def test_detect_with_period_filters_output_not_input():
    tb, day = make_toolbox()
    full = tb.dispatch("detect_anomalies", {"signal": "유동인구", "emd": "서귀포시 성산읍"}, "R1").data
    near = tb.dispatch("detect_anomalies", {"signal": "유동인구", "emd": "서귀포시 성산읍",
                                            "start": str((day - pd.Timedelta(days=3)).date()),
                                            "end": str((day + pd.Timedelta(days=3)).date())}, "R2").data
    assert full["count"] >= 1 and [a["date"] for a in near["anomalies"]] == [str(day.date())]
    assert near["anomalies"][0]["expected"] == full["anomalies"][0]["expected"]  # 같은 기준선


def test_co_movements_can_exclude_the_analysed_signal():
    tb, day = make_toolbox()
    data = tb.dispatch("find_co_movements", {"date": str(day.date()), "emd": "서귀포시 성산읍", "exclude_signal": "유동인구"}, "R1").data
    assert "유동인구" not in data["checked"]
