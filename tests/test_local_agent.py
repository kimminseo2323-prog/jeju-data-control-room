import pandas as pd

from app.agent.local import Slots, answer, parse_slots, route, rule_route
from app.agent.tools import MemoryStore, Toolbox
from app.llm.judge import Judgment
from app.rag.index import build_index
from tests.test_detect import weekly_series

LO, HI = pd.Timestamp("2024-04-01"), pd.Timestamp("2025-03-31")


def test_parse_emd_date_and_signal():
    s = parse_slots("이호동 7월 28일에 사람이 왜 이렇게 많았어?", LO, HI)
    assert s.emd == "제주시 이호동" and s.date == pd.Timestamp("2024-07-28") and s.signal == "유동인구"


def test_parse_month_part_and_wifi():
    s = parse_slots("애월읍 와이파이 이용자가 12월 말에 급증한 이유", LO, HI)
    assert s.emd == "제주시 애월읍" and s.signal == "와이파이" and s.date is None
    assert (s.start, s.end) == (pd.Timestamp("2024-12-21"), pd.Timestamp("2024-12-31"))


def test_parse_month_in_next_year_of_range():
    s = parse_slots("1월에 버스 이상한 곳", LO, HI)
    assert (s.start, s.end, s.signal, s.emd) == (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-31"), "버스", None)


def test_parse_holiday_name_and_short_emd():
    s = parse_slots("어린이날에 왜 연동 유동인구가 늘었지", LO, HI)
    assert s.emd == "제주시 연동" and s.date == pd.Timestamp("2024-05-05")


def test_rule_route_keywords():
    assert rule_route("성산읍 왜 늘었어") == "explain"
    assert rule_route("버스 데이터 출처가 어디야") == "docs"
    assert rule_route("7월 이상 신호 목록") == "scan"
    assert rule_route("점심 메뉴 추천") == "other"


class FakeHTTP:
    def __init__(self, choice=None, models=("tev1:4b",)):
        self.choice, self.models, self.posted = choice, list(models), 0

    def get(self, url, timeout=None):
        if self.choice is None:
            raise ConnectionError("down")
        names = self.models

        class T:
            def raise_for_status(self):
                pass

            def json(self):
                return {"models": [{"name": n} for n in names]}
        return T()

    def post(self, url, json=None, timeout=None):
        self.posted += 1
        if self.choice is None:
            raise ConnectionError("down")
        choice = self.choice

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"answers": {"intent": {"choice": choice, "confidence": 0.9, "probabilities": {choice: 0.9}}}}
        return R()


def test_route_sends_question_only_to_verified_local_model():
    h = FakeHTTP("docs", models=["gemma4-12b-agent"])
    intent, _, backend = route("버스 데이터 출처가 어디야", http=h)
    assert h.posted == 0 and backend == "rule" and intent == "docs"


def test_route_uses_local_model_then_falls_back():
    assert route("아무 질문", http=FakeHTTP("docs"))[0:2] == ("docs", 0.9)
    intent, _, backend = route("성산읍 왜 늘었어", http=FakeHTTP(None))
    assert intent == "explain" and backend == "rule"


def _toolbox():
    s = weekly_series(days=200)          # 2024-10-01 ~
    s[pd.Timestamp("2024-12-28")] += 700
    calm = weekly_series(days=200, seed=4)
    store = MemoryStore(series={("유동인구", "제주시 이호동"): s, ("유동인구", "제주시 연동"): calm})
    idx = build_index([{"doc_id": "api_583", "title": "유동인구 API", "locator": "허브 583",
                        "text": "visitPop 은 방문인구 수이며 일일 쿼터 1,000건이다."},
                       {"doc_id": "api_613", "title": "버스 API", "locator": "허브 613", "text": "userCount 는 정류소별 승차 인원이다."},
                       {"doc_id": "notice", "title": "반출 기준", "locator": "공지 48", "text": "센터 분석 결과물은 검토 후 반출한다."}])
    return Toolbox(store, idx)


def fake_judge(evidence):
    return Judgment("tourism_demand", {"tourism_demand": 0.71, "unknown": 0.29}, 0.7, "tev1:4b")


def test_explain_flow_runs_tools_judges_and_verifies():
    run = answer("이호동 12월 28일 유동인구가 왜 늘었어?", _toolbox(), http=FakeHTTP("explain"), judge=fake_judge)
    assert run.intent == "explain" and run.verified, run.verify_errors
    assert [r.tool for r in run.results.values()] == ["detect_anomalies", "find_co_movements", "check_context", "judge_cause"]
    assert "관광 수요 변화" in run.final_text and "71.0" in run.final_text and "[R4]" in run.final_text


def test_explain_without_region_asks_for_it():
    run = answer("왜 늘었어?", _toolbox(), http=FakeHTTP("explain"), judge=fake_judge)
    assert run.results == {} and "읍면동" in run.final_text


def test_scan_flow_lists_regions_with_anomalies():
    run = answer("12월에 유동인구 이상했던 곳", _toolbox(), http=FakeHTTP("scan"), judge=fake_judge)
    assert run.intent == "scan" and run.verified, run.verify_errors
    assert "제주시 이호동" in run.final_text and "2024-12-28" in run.final_text


def test_docs_flow_cites_passages():
    run = answer("visitPop 뜻이 뭐야", _toolbox(), http=FakeHTTP("docs"), judge=fake_judge)
    assert run.intent == "docs" and run.verified and "허브 583" in run.final_text and "[R1]" in run.final_text


def test_other_flow_states_scope():
    run = answer("점심 메뉴 추천해줘", _toolbox(), http=FakeHTTP("other"), judge=fake_judge)
    assert run.results == {} and "다루지 않습니다" in run.final_text


def test_docs_titles_with_numbered_headings_still_verify():
    idx = build_index([{"doc_id": "qa3", "title": "게시판 답변 — 3. 반출 기준", "locator": "답변 정리 §3. 반출", "text": "결과물 반출은 검토 후 가능하다. 원본 데이터는 반출 불가."},
                       {"doc_id": "a", "title": "버스", "locator": "허브 613", "text": "정류소 승차 인원"},
                       {"doc_id": "b", "title": "기상", "locator": "허브 579", "text": "일강수량 풍속"}])
    tb = Toolbox(MemoryStore(series={("유동인구", "제주시 연동"): weekly_series()}), idx)
    run = answer("반출 기준이 뭐야", tb, http=FakeHTTP("docs"), judge=fake_judge)
    assert run.verified, run.verify_errors


def test_snippet_drops_markdown_table_syntax():
    from app.agent.local import _snippet
    s = _snippet("| 질문 | 공식 답변 | |---|---| | 원본을 외부 LLM에 | **불가** (10/30) |")
    assert "|" not in s and "---" not in s and "**" not in s and "불가 (10/30)" in s


def test_rule_rescues_in_scope_question_model_called_other():
    intent, _, backend = route("버스 데이터 출처가 어디야", http=FakeHTTP("other"))
    assert intent == "docs" and backend.endswith("+rule")


def test_model_other_kept_when_rule_agrees():
    intent, prob, backend = route("점심 메뉴 추천해줘", http=FakeHTTP("other"))
    assert (intent, backend) == ("other", "tev1:4b") and prob == 0.9


def test_parse_foreign_visitor_signal():
    from app.agent.local import parse_slots
    lo, hi = pd.Timestamp("2024-04-01"), pd.Timestamp("2026-08-31")
    assert parse_slots("성산읍 외국인 관광객이 7월 28일에 왜 늘었어?", lo, hi).signal == "외국인"
    assert parse_slots("성산읍 7월 28일에 왜 사람이 많았어?", lo, hi).signal == "유동인구"


def test_yearless_date_means_most_recent_year_in_data():
    """데이터가 여러 해(2024-04~2026-08)면 연도 없는 '7월 28일'·'7월'·'어린이날'은 가장 최근 해로 본다."""
    lo, hi = pd.Timestamp("2024-04-01"), pd.Timestamp("2026-08-31")
    assert parse_slots("이호동 7월 28일에 왜 사람이 많았어?", lo, hi).date == pd.Timestamp("2026-07-28")
    s = parse_slots("10월에 유동인구 이상한 곳", lo, hi)
    assert (s.start, s.end) == (pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-31"))   # 2026-10은 데이터 밖
    assert parse_slots("어린이날에 연동 왜 늘었어", lo, hi).date == pd.Timestamp("2026-05-05")


def test_cause_sentence_says_who_chose_it():
    """답변 문장은 템플릿이 만들고, 원인 후보를 고른 주체(판단 모델 tev1 / 규칙)를 밝힌다. 규칙일 때는 고정 확률을 보이지 않는다."""
    from app.llm.judge import rule_judge
    by_model = answer("이호동 12월 28일 유동인구가 왜 늘었어?", _toolbox(), http=FakeHTTP("explain"), judge=fake_judge)
    by_rule = answer("이호동 12월 28일 유동인구가 왜 늘었어?", _toolbox(), http=FakeHTTP(None), judge=rule_judge)
    assert "판단 모델(tev1)이 근거를 보고 고른 원인 후보" in by_model.final_text and "71.0%" in by_model.final_text
    last = [l for l in by_rule.final_text.splitlines() if "원인 후보" in l][-1]
    assert "규칙으로 고른 원인 후보" in last and "%" not in last and by_rule.verified, by_rule.verify_errors


def test_judgment_added_to_detail_briefing_still_verifies():
    # 상세 분석 탭에서 원인 판정을 실행해도 브리핑(저장 HTML 포함)에 판정이 빠져 있었다(2026-11-17). 질문하기와 같은 문장을 붙인다
    from app.agent.local import add_judgment
    from app.agent.verify import verify
    from app.report.briefing import template_text
    from tests.test_briefing import RESULTS
    evidence = {"anomaly": {"emd": "서귀포시 성산읍", "signal": "유동인구", "date": "2025-01-29", "pct": 35.4, "kind": "일시 급변", "days": 1},
                "context": RESULTS["R2"].data["items"], "co_movements": [], "not_covered": [], "co_checked": [], "co_no_data": []}
    res = dict(RESULTS)
    text = add_judgment(template_text(res), res, Judgment("holiday", {"holiday": 0.87, "unknown": 0.13}, 0.87, "tev1:4b"), evidence, refs=["R2"])
    assert "R3" in res and res["R3"].tool == "judge_cause"
    assert "판단 모델(tev1)이 근거를 보고 고른 원인 후보는 '공휴일·연휴'(확률 87.0%, 확신도 상)입니다 [R3][R2]." in text
    assert text.endswith("이는 상관에 기반한 후보이며 인과를 뜻하지 않습니다.") and verify(text, res).ok, verify(text, res).errors
    res2 = dict(RESULTS)
    text2 = add_judgment(template_text(res2), res2, Judgment("holiday", {"holiday": 0.75}, 0.75, "rule"), evidence, refs=["R2"])
    last = [l for l in text2.splitlines() if "원인 후보" in l][-1]
    assert "규칙으로 고른 원인 후보" in last and "%" not in last and verify(text2, res2).ok
