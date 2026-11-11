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
