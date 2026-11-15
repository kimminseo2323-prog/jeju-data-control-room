"""2026-11-15 코드 점검에서 찾은 문제들의 재현 테스트."""
import pandas as pd
import pytest

from app.agent.local import answer
from app.agent.loop import LLMReply, ToolCall, run_agent
from app.agent.tools import MemoryStore, Toolbox
from app.llm.judge import Judgment, evidence_text, judgment_label, rule_judge
from tests.test_agent import ScriptedLLM, make_toolbox
from tests.test_detect import weekly_series
from tests.test_hub_client import QuotaSession, make_client
from tests.test_local_agent import FakeHTTP, _toolbox, fake_judge


# 1. 없는 날짜
@pytest.mark.parametrize("q", ["이호동 2월 30일에 왜 많았어?", "이호동 2025-02-30 유동인구 왜 늘었어?", "13월에 이상한 곳 알려줘"])
def test_impossible_date_gets_a_message_not_a_crash(q):
    run = answer(q, _toolbox(), http=FakeHTTP("explain"), judge=fake_judge)
    assert run.verified and "없는 날짜" in run.final_text


# 2. 규칙 판정은 확률·확신도를 보이지 않는다
def test_rule_judgment_label_has_no_probability():
    label = judgment_label(rule_judge({"context": [{"kind": "holiday"}]}))
    assert "규칙" in label and "%" not in label and "확신도" not in label


def test_model_judgment_label_shows_probability():
    label = judgment_label(Judgment("holiday", {"holiday": 0.82, "unknown": 0.18}, 0.8, "tev1:4b"))
    assert "82%" in label and "확신도 상" in label and "tev1" in label


# 3. 그날 자료가 없는 신호는 '평소 수준'이 아니라 '자료 없음'
def _store_with_short_bus():
    pop = weekly_series(days=200)
    bus = weekly_series(days=60, seed=3)          # 2024-10-01 ~ 2024-11-29만 있음
    return MemoryStore(series={("유동인구", "제주시 연동"): pop, ("버스", "제주시 연동"): bus}), pop.index[150]


def test_co_movements_separate_signals_without_data():
    store, day = _store_with_short_bus()
    d = Toolbox(store, None).dispatch("find_co_movements", {"date": str(day.date()), "emd": "제주시 연동", "exclude_signal": "유동인구"}, "R1").data
    assert "버스" in d["no_data"] and "제주 전체 버스" in d["no_data"]
    assert "버스" not in d["checked"] and "제주 전체 유동인구" in d["checked"]


def test_evidence_text_does_not_call_missing_signals_normal():
    ev = {"anomaly": {"emd": "제주시 연동", "signal": "유동인구", "date": "2025-05-01", "pct": 40.0, "kind": "일시 급변", "days": 1},
          "context": [], "co_movements": [], "co_checked": ["제주 전체 유동인구"], "co_no_data": ["버스", "제주 전체 버스"]}
    t = evidence_text(ev)
    assert "자료 없음" in t and "버스" in t
    normal_line = next(l for l in t.splitlines() if "평소 수준" in l)
    assert "버스" not in normal_line and "제주 전체 유동인구" in normal_line


def test_evidence_text_when_no_other_signal_has_data():
    ev = {"anomaly": {"emd": "제주시 연동", "signal": "유동인구", "date": "2025-05-01", "pct": 40.0, "kind": "일시 급변", "days": 1},
          "context": [], "co_movements": [], "co_checked": [], "co_no_data": ["버스"]}
    assert "평소 수준" not in evidence_text(ev)


# 4. 수집 계획이 실제 분석 기간과 같아야 한다(옛 계획으로 다시 받으면 캐시가 줄어듦)
def test_collection_plan_covers_analysis_period():
    from app.ingest.plan import PLAN
    plan = {job: (s, e) for job, s, e in PLAN}
    assert plan["pop_domestic"] == ("2024-04-01", "2026-08-31")
    assert plan["pop_foreign_short"] == ("2024-04-01", "2026-08-31")


# 5. 403은 쿼터 초과로 단정하지 않는다
def test_403_message_does_not_assert_quota(tmp_path):
    from app.ingest.hub_client import QuotaExceeded
    with pytest.raises(QuotaExceeded) as e:
        make_client(tmp_path, QuotaSession(ok_calls=0)).fetch_all("API1", {"d": "1"})
    assert e.value.http403 and "403" in str(e.value) and "프로젝트" in e.value.hint()


# 6. 국적별 변화: 기준값을 못 구한 국적은 0으로 치지 않고 뺀다
def test_nationality_without_baseline_is_skipped():
    idx = pd.date_range("2024-10-01", periods=100, freq="D")
    nat = pd.DataFrame({"중국": 100.0, "몽골": float("nan")}, index=idx)
    day = idx[70]
    nat.loc[day, "몽골"] = 40.0            # 평소 기록이 없는 국적
    store = MemoryStore(series={("외국인", "제주시 연동"): nat.sum(axis=1)}, nationality={"제주시 연동": nat})
    d = Toolbox(store, None).dispatch("nationality_mix", {"date": str(day.date()), "emd": "제주시 연동"}, "R1").data
    assert all(r["nationality"] != "몽골" for r in d["top"]) and "몽골" in d["no_baseline"]


# 7. 기간을 줘도 이상 구간은 잘리지 않는다(관제판과 같은 일수·유형)
def test_period_does_not_truncate_episode():
    s = weekly_series()
    days = s.index[70:76]
    s[days] = s[days] + 500                # 6일 연속
    tb = Toolbox(MemoryStore(series={("유동인구", "제주시 연동"): s}), None)
    d = tb.dispatch("detect_anomalies", {"signal": "유동인구", "emd": "제주시 연동", "start": str(s.index[60].date()),
                                         "end": str(s.index[72].date())}, "R1").data
    ep = d["episodes"][0]
    assert ep["days"] == 6 and ep["end"] == str(days[-1].date()) and ep["kind"] == "지속 변화"


# 9. 외부 LLM 루프가 한도에 걸리면 검증 안 된 문장을 보이지 않는다
def test_max_steps_does_not_show_unverified_text():
    tb, _ = make_toolbox()
    reply = LLMReply(text="방문객이 99999명 늘었습니다", tool_calls=[ToolCall("c", "search_docs", {"query": "visitPop"})])
    run = run_agent("질문", ScriptedLLM([reply] * 10), tb, max_steps=2)
    assert run.stopped and not run.verified and "99999" not in run.final_text


def test_foreign_plan_skips_months_with_hub_source_error():
    """589의 2025-04·05는 허브 원천 오류(HTTP 500)라 받을 수 없다 — 계획대로 다시 받을 때 그 달에서 멈추지 않게 건너뛴다."""
    import datetime as dt
    from app.ingest.jobs import JOBS, expand
    starts = [r["startDate"] for r in expand(JOBS["pop_foreign_short"], dt.date(2025, 3, 1), dt.date(2025, 6, 30))]
    assert starts == ["20250301", "20250601"]
