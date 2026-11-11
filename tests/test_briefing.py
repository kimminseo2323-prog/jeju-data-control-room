import pandas as pd

from app.agent.loop import AgentRun
from app.agent.tools import ToolResult
from app.agent.verify import verify
from app.report.briefing import ResultStore, render_briefing, template_text

RESULTS = {
    "R1": ToolResult("R1", "detect_anomalies", {"signal": "유동인구", "emd": "서귀포시 성산읍"},
                     {"signal": "유동인구", "emd": "서귀포시 성산읍", "method": "seasonal_z", "threshold": 3.0, "count": 1,
                      "anomalies": [{"date": "2025-01-29", "value": 1353.5, "expected": 1000.0, "pct": 35.4, "score": 4.1, "direction": "up"}]},
                     ["제주데이터허브 읍면동 단위 내국인 유동인구(583)"]),
    "R2": ToolResult("R2", "check_context", {"date": "2025-01-29", "emd": "서귀포시 성산읍"},
                     {"date": "2025-01-29", "emd": "서귀포시 성산읍", "items": [{"kind": "holiday", "detail": "설날 (당일, 2025-01-29)"}]},
                     ["holidays 오픈소스 패키지(대한민국 공휴일)"]),
}


def test_template_text_passes_verifier_and_mentions_context():
    text = template_text(RESULTS)
    assert "35.4" in text and "설날" in text
    assert verify(text, RESULTS).ok, verify(text, RESULTS).errors


def test_briefing_html_has_asof_sources_and_verification_status():
    run = AgentRun("성산읍 이상 신호?", [], results=RESULTS, final_text="본문 [R1].", verified=True)
    html = render_briefing(run, generated_at=pd.Timestamp("2026-11-10 17:00"), data_as_of={"유동인구": "2026-08-31"})
    for s in ["데이터 기준일", "2026-08-31", "출처", "제주데이터허브 읍면동 단위 내국인 유동인구(583)", "검증 통과", "2026-11-10 17:00"]:
        assert s in html
    assert "<table" in html


def test_unverified_briefing_is_marked():
    run = AgentRun("q", [], results=RESULTS, final_text="x", verified=False)
    assert "검증 미통과" in render_briefing(run, generated_at=pd.Timestamp("2026-11-10"), data_as_of={})


def test_result_store_delete_on_removes_files(tmp_path):
    st = ResultStore(tmp_path, delete_on_exit=True)
    p = st.save("briefing", "<html></html>")
    assert p.exists()
    st.cleanup()
    assert not p.exists()


def test_result_store_delete_off_keeps_files(tmp_path):
    st = ResultStore(tmp_path, delete_on_exit=False)
    p = st.save("briefing", "<html></html>")
    st.cleanup()
    assert p.exists()


def test_template_with_episodes_passes_verifier():
    r = dict(RESULTS)
    d = dict(r["R1"].data)
    d["episode_count"] = 1
    d["episodes"] = [{"start": "2025-01-28", "end": "2025-01-30", "days": 3, "kind": "지속 변화", "direction": "up",
                      "peak_date": "2025-01-29", "peak_pct": 35.4, "peak_value": 1353.5, "peak_expected": 1000.0}]
    r["R1"] = ToolResult("R1", "detect_anomalies", {}, d, ["허브 583"])
    text = template_text(r)
    assert "지속 변화" in text and "2025-01-28~2025-01-30" in text and "설날" in text
    assert verify(text, r).ok, verify(text, r).errors


def test_template_mentions_co_movements_with_citation():
    res = {**RESULTS, "R3": ToolResult("R3", "find_co_movements", {"date": "2025-01-29", "emd": "서귀포시 성산읍"},
                                       {"date": "2025-01-29", "emd": "서귀포시 성산읍", "checked": ["제주 전체 유동인구"],
                                        "co_movements": [{"signal": "제주 전체 유동인구", "date": "2025-01-30", "z": 5.21, "direction": "up"}]},
                                       ["제주데이터허브 읍면동 단위 내국인 유동인구(583)"])}
    text = template_text(res)
    line = [l for l in text.splitlines() if "제주 전체 유동인구" in l]
    assert len(line) == 1 and "5.21" in line[0] and "[R3]" in line[0]
    assert verify(text, res).ok, verify(text, res).errors


def test_no_anomaly_sentence_states_checked_period():
    res = {"R1": ToolResult("R1", "detect_anomalies", {}, {"signal": "유동인구", "emd": "제주시 연동", "start": "2024-04-21", "end": "2024-05-19",
                                                           "count": 0, "anomalies": [], "episodes": [], "episode_count": 0}, ["허브 583"])}
    text = template_text(res)
    assert "2024-04-21~2024-05-19" in text and verify(text, res).ok


def test_template_for_decrease_passes_verifier():
    res = {"R1": ToolResult("R1", "detect_anomalies", {}, {"signal": "와이파이", "emd": "제주시 연동", "start": None, "end": None, "count": 1,
                                                           "episode_count": 1, "anomalies": [{"date": "2025-01-14", "value": 492.0, "expected": 950.0, "pct": -48.2, "score": -4.1, "direction": "down"}],
                                                           "episodes": [{"start": "2025-01-14", "end": "2025-01-14", "days": 1, "kind": "일시 급변", "direction": "down",
                                                                         "peak_date": "2025-01-14", "peak_pct": -48.2, "peak_value": 492.0, "peak_expected": 950.0, "peak_score": -4.1}]}, ["허브"])}
    text = template_text(res)
    assert "적었" in text and verify(text, res).ok, verify(text, res).errors


def test_result_store_purge_deletes_even_when_keep_on_exit(tmp_path):
    st = ResultStore(tmp_path, delete_on_exit=False)
    p = st.save("briefing", "<html></html>")
    assert st.purge() == 1 and not p.exists() and st.saved == []


def test_opposite_season_is_not_called_a_cause_candidate():
    # 급증인데 비수기(-15.1%)를 '원인 후보'로 쓰면 앞뒤가 맞지 않는다(삼도1동 2025-03-30)
    r = dict(RESULTS)
    r["R2"] = ToolResult("R2", "check_context", {}, {"date": "2025-01-29", "emd": "서귀포시 성산읍", "items": [
        {"kind": "holiday", "detail": "설날 (당일, 2025-01-29)"},
        {"kind": "visitors", "detail": "2025-01 입도객 100.0만 명, 주변 12개월 평균 대비 -15.1%(비수기)", "value": -15.1}]}, ["허브 580"])
    text = template_text(r)
    cand = [l for l in text.split("\n") if "원인 후보로 볼 수" in l]
    assert len(cand) == 1 and "설날" in cand[0] and "비수기" not in cand[0]
    assert any("비수기" in l and "반대" in l for l in text.split("\n"))
    assert verify(text, r).ok, verify(text, r).errors


def test_markdown_safe_keeps_date_ranges_from_strikethrough():
    # 화면(st.markdown)은 '~'가 두 번 나오면 그 사이를 취소선으로 그린다(질문하기 탭에서 발견, 2026-11-11)
    from app.report.briefing import markdown_safe
    out = markdown_safe("2024-07-26~2024-07-29(지속 변화) [R1].\n2024-07-31~2024-08-02(지속 변화) [R1].")
    assert "~" not in out.replace("\~", "")
    assert out.count("  \n") == 1   # 줄바꿈 유지


def test_template_says_context_not_checked_outside_source_period():
    from app.agent.tools import ToolResult
    from app.agent.verify import verify
    from app.report.briefing import template_text
    res = {"R1": ToolResult("R1", "detect_anomalies", {}, {"signal": "유동인구", "emd": "제주시 이호동", "count": 1, "anomalies": [
               {"date": "2025-08-02", "value": 150.0, "expected": 100.0, "pct": 50.0, "score": 5.0, "direction": "up"}]}),
           "R2": ToolResult("R2", "check_context", {}, {"date": "2025-08-02", "emd": "제주시 이호동", "items": [], "not_covered": ["weather", "event"]})}
    text = template_text(res)
    assert "기상·축제·행사 자료 제공 기간 밖이라 확인하지 못했습니다 [R2]" in text
    assert verify(text, res).ok


def test_template_reports_nationality_driving_the_change():
    from app.agent.tools import ToolResult
    from app.agent.verify import verify
    from app.report.briefing import template_text
    res = {"R1": ToolResult("R1", "detect_anomalies", {}, {"signal": "외국인", "emd": "제주시 건입동", "count": 1, "anomalies": [
               {"date": "2024-07-28", "value": 2400.0, "expected": 1000.0, "pct": 140.0, "score": 8.0, "direction": "up"}]}),
           "R2": ToolResult("R2", "nationality_mix", {}, {"date": "2024-07-28", "emd": "제주시 건입동", "total_diff": 1400.0, "nationalities": 12,
                                                          "top": [{"nationality": "중국", "value": 1800.0, "expected": 600.0, "diff": 1200.0, "share_of_change": 85.7},
                                                                  {"nationality": "대만", "value": 300.0, "expected": 200.0, "diff": 100.0, "share_of_change": 7.1}]})}
    text = template_text(res)
    assert "국적별로는 중국이 평소보다 1,200.0명 많아 전체 변화의 85.7%를 차지했습니다 [R2]." in text
    assert verify(text, res).ok
