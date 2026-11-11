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
    assert names == {"get_series", "detect_anomalies", "scan_regions", "find_co_movements", "check_context", "search_docs"}


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


def test_check_context_tool_passes_visitor_value_through():
    idx = pd.date_range("2024-04-01", "2025-03-01", freq="MS")
    v = pd.Series(1_000_000.0, index=idx)
    v[pd.Timestamp("2024-08-01")] = 1_300_000.0
    tb = Toolbox(MemoryStore(series={}, visitors=v), index=None)
    r = tb.dispatch("check_context", {"date": "2024-08-10", "emd": "제주시 이호동"}, "R1")
    vis = [i for i in r.data["items"] if i["kind"] == "visitors"]
    assert len(vis) == 1 and vis[0]["value"] > 0 and any("580" in s for s in r.sources)


def test_co_movements_include_island_wide_total():
    a, b = weekly_series(seed=1), weekly_series(seed=2)
    day = a.index[70]
    a[day] += 400
    b[day] += 400   # 두 읍면동이 함께 늘면 제주 전체 합계도 튄다
    tb = Toolbox(MemoryStore(series={("유동인구", "제주시 이호동"): a, ("유동인구", "제주시 연동"): b}), index=None)
    r = tb.dispatch("find_co_movements", {"date": str(day.date()), "emd": "제주시 이호동", "exclude_signal": "유동인구"}, "R1")
    assert [m["signal"] for m in r.data["co_movements"]] == ["제주 전체 유동인구"]
    assert "제주 전체 유동인구" in r.data["checked"]


def test_scan_regions_ranks_episodes_across_regions():
    a, b = weekly_series(seed=1), weekly_series(seed=2)
    a[a.index[70]] += 600
    b[b.index[90]] += 300
    tb = Toolbox(MemoryStore(series={("유동인구", "제주시 이호동"): a, ("유동인구", "제주시 연동"): b}), index=None)
    r = tb.dispatch("scan_regions", {"signal": "유동인구", "threshold": 3.5}, "R1")
    assert r.data["checked"] == 2 and r.data["with_anomalies"] == 2
    assert [e["emd"] for e in r.data["episodes"]][:2] == ["제주시 이호동", "제주시 연동"]


def test_detect_output_records_requested_period():
    tb, day = make_toolbox()
    r = tb.dispatch("detect_anomalies", {"signal": "유동인구", "emd": "서귀포시 성산읍", "start": "2024-12-01", "end": "2024-12-20"}, "R1")
    assert r.data["start"] == "2024-12-01" and r.data["end"] == "2024-12-20"


def test_island_total_excludes_the_region_itself():
    # 한 읍면동만 크게 튀면 그 값이 섞인 '제주 전체'도 튄다 → 섬 전체 흐름으로 오판(삼도1동 2025-03-29, 와이파이 점수 13.7)
    a, b = weekly_series(seed=1), weekly_series(seed=2)
    day = a.index[70]
    a[day] += 4000   # 이호동만 증가
    tb = Toolbox(MemoryStore(series={("와이파이", "제주시 이호동"): a, ("와이파이", "제주시 연동"): b}), index=None)
    r = tb.dispatch("find_co_movements", {"date": str(day.date()), "emd": "제주시 이호동"}, "R1")
    assert [m["signal"] for m in r.data["co_movements"]] == ["와이파이"]   # 자기 신호만, 제주 전체는 아님


def test_neighbors_moving_together_are_reported():
    """주변 읍면동도 같은 날 함께 늘면 '인근 읍면동' 동반 변화로 보고한다(국지 행사 vs 광역 흐름 구분 근거)."""
    a, b, c, far = (weekly_series(seed=k) for k in (1, 2, 3, 4))
    day = a.index[70]
    for s in (a, b, c):
        s[day] += 400
    store = MemoryStore(series={("유동인구", "제주시 이호동"): a, ("유동인구", "제주시 도두동"): b,
                                ("유동인구", "제주시 외도동"): c, ("유동인구", "서귀포시 성산읍"): far},
                        neighbors={"제주시 이호동": ["제주시 도두동", "제주시 외도동"]})
    r = Toolbox(store, index=None).dispatch("find_co_movements", {"date": str(day.date()), "emd": "제주시 이호동",
                                                                  "exclude_signal": "유동인구"}, "R1")
    sigs = [m["signal"] for m in r.data["co_movements"]]
    assert "인근 읍면동 유동인구" in sigs
    assert r.data["neighbors"] == ["제주시 도두동", "제주시 외도동"]


def test_neighbors_quiet_when_only_the_region_moves():
    a, b, c = (weekly_series(seed=k) for k in (1, 2, 3))
    day = a.index[70]
    a[day] += 400
    store = MemoryStore(series={("유동인구", "제주시 이호동"): a, ("유동인구", "제주시 도두동"): b, ("유동인구", "제주시 외도동"): c},
                        neighbors={"제주시 이호동": ["제주시 도두동", "제주시 외도동"]})
    r = Toolbox(store, index=None).dispatch("find_co_movements", {"date": str(day.date()), "emd": "제주시 이호동",
                                                                  "exclude_signal": "유동인구"}, "R1")
    assert "인근 읍면동 유동인구" not in [m["signal"] for m in r.data["co_movements"]]


def test_same_week_last_year_anomaly_is_context():
    """작년 같은 주(52주 전 ±3일)에도 같은 방향 이상이 있었으면 '매년 반복' 맥락으로 알려 준다."""
    idx = pd.date_range("2024-01-01", periods=600, freq="D")
    s = weekly_series(days=600, seed=3)
    s.index = idx
    last, now = pd.Timestamp("2024-07-28"), pd.Timestamp("2025-07-27")   # 364일 차이(같은 요일)
    s[last] += 600
    s[now] += 600
    tb = Toolbox(MemoryStore(series={("유동인구", "제주시 이호동"): s}), index=None)
    r = tb.dispatch("check_context", {"date": "2025-07-27", "emd": "제주시 이호동", "signal": "유동인구"}, "R1")
    rec = [i for i in r.data["items"] if i["kind"] == "recurrence"]
    assert rec and "2024-07-28" in rec[0]["detail"] and "작년" in rec[0]["detail"]


def test_no_recurrence_item_without_last_year_data():
    tb, day = make_toolbox()   # 데이터가 1년 미만
    r = tb.dispatch("check_context", {"date": str(day.date()), "emd": "서귀포시 성산읍", "signal": "유동인구"}, "R1")
    assert not [i for i in r.data["items"] if i["kind"] == "recurrence"]


def test_context_outside_source_period_is_marked_not_covered():
    """기상 자료가 끝난 뒤의 날짜는 '기상 특이사항 없음'이 아니라 '확인 불가'여야 한다(허브 기상은 2025-03까지)."""
    store = MemoryStore(series={}, coverage={"weather": (pd.Timestamp("2024-04-01"), pd.Timestamp("2025-03-30")),
                                             "event": (pd.Timestamp("2012-07-18"), pd.Timestamp("2025-03-22"))})
    tb = Toolbox(store, index=None)
    late = tb.dispatch("check_context", {"date": "2025-08-02", "emd": "제주시 이호동"}, "R1")
    early = tb.dispatch("check_context", {"date": "2024-08-02", "emd": "제주시 이호동"}, "R2")
    assert late.data["not_covered"] == ["weather", "event"]
    assert early.data["not_covered"] == []
