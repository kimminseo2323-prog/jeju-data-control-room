from app.agent.tools import ToolResult
from app.agent.verify import verify

R = {
    "R1": ToolResult("R1", "detect_anomalies", {}, {"anomalies": [{"date": "2025-01-29", "value": 1353.5, "expected": 1000.0, "pct": 35.4}]}, ["허브 583"]),
    "R2": ToolResult("R2", "find_co_movements", {}, {"co_movements": [{"signal": "버스", "date": "2025-01-29", "z": 4.2}]}, ["허브 613"]),
    "R3": ToolResult("R3", "check_context", {}, {"items": [{"kind": "holiday", "detail": "설날 (당일, 2025-01-29)"}]}, ["holidays"]),
}


def test_matching_numbers_with_citation_pass():
    v = verify("2025년 1월 29일 성산읍 방문인구는 1,353.5명으로 기대값 1000명보다 35.4% 많았습니다 [R1].", R)
    assert v.ok, v.errors


def test_rounded_integer_of_value_is_allowed():
    assert verify("방문인구는 약 1,354명이었습니다 [R1].", R).ok


def test_changed_number_fails():
    v = verify("방문인구는 1,500명이었습니다 [R1].", R)
    assert not v.ok and any("1500" in e or "1,500" in e for e in v.errors)


def test_number_without_citation_fails():
    v = verify("방문인구가 35.4% 늘었습니다.", R)
    assert not v.ok and any("근거" in e for e in v.errors)


def test_unknown_result_id_fails():
    assert not verify("방문인구가 35.4% 늘었습니다 [R9].", R).ok


def test_cause_claim_needs_context_or_co_movement_evidence():
    assert not verify("원인 후보는 설 연휴입니다 [R1].", R).ok
    assert verify("원인 후보는 설 연휴입니다(확신도 상) [R3].", R).ok


def test_assertive_cause_wording_warns():
    v = verify("방문인구 증가는 설 연휴 때문입니다 [R3].", R)
    assert v.ok and v.warnings


def test_numbers_inside_place_names_are_ignored():
    assert verify("제주시 일도1동은 이상 신호가 없었습니다.", R).ok


def test_comma_grouped_number_inside_cited_text_matches():
    r = {"R1": ToolResult("R1", "search_docs", {}, {"passages": [{"text": "일일 쿼터 1,000건"}]}, ["허브"])}
    assert verify("문서에 따르면 일일 쿼터는 1,000건입니다 [R1].", r).ok
