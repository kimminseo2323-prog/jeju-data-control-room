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


def test_decrease_written_as_magnitude_passes():
    r = {"R1": ToolResult("R1", "detect_anomalies", {}, {"anomalies": [{"date": "2025-01-14", "value": 492.0, "expected": 950.0, "pct": -48.2}]}, ["허브"])}
    v = verify("2025-01-14 값은 492.0명으로 기대값 950.0보다 48.2% 적었습니다 [R1].", r)
    assert v.ok, v.errors


def test_changed_date_fails_even_if_parts_exist_elsewhere():
    r = {"R1": ToolResult("R1", "detect_anomalies", {}, {"anomalies": [{"date": "2024-10-03", "value": 5.0}, {"date": "2024-12-01", "value": 7.0}]}, ["허브"])}
    assert verify("2024-10-03 값은 5.0명이었습니다 [R1].", r).ok
    assert not verify("2024-12-03 값은 5.0명이었습니다 [R1].", r).ok


def test_small_count_cannot_hide_in_date_parts():
    r = {"R1": ToolResult("R1", "detect_anomalies", {}, {"count": 4, "anomalies": [{"date": "2024-10-19"}]}, ["허브"])}
    assert verify("이상일은 4일입니다 [R1].", r).ok
    assert not verify("이상일은 19일입니다 [R1].", r).ok


def test_korean_month_day_checked_as_date():
    assert verify("1월 29일 방문인구는 1,353.5명이었습니다 [R1].", R).ok
    assert not verify("1월 28일 방문인구는 1,353.5명이었습니다 [R1].", R).ok


def test_integer_tolerance_is_rounding_only():
    r = {"R1": ToolResult("R1", "detect_anomalies", {}, {"threshold": 3.5, "count": 1}, ["허브"])}
    assert verify("이상 구간은 1개입니다 [R1].", r).ok
    assert not verify("이상 구간은 3개입니다 [R1].", r).ok


def test_decimal_written_number_uses_decimal_tolerance():
    r = {"R2": ToolResult("R2", "find_co_movements", {}, {"co_movements": [{"z": 7.24}]}, ["허브"])}
    assert verify("점수 7.24입니다 [R2].", r).ok
    assert not verify("점수 7.0입니다 [R2].", r).ok


def test_digit_inside_place_name_is_not_evidence():
    # '용담1동'의 1은 지명이지 수치가 아니다 → 지명만 담은 결과로 '1개'를 뒷받침할 수 없다(검증기 평가에서 발견, 2026-11-11)
    r = {"R1": ToolResult("R1", "detect_anomalies", {}, {"emd": "제주시 용담1동", "count": 1}, ["허브"]),
         "R3": ToolResult("R3", "check_context", {}, {"date": "2024-12-30", "emd": "제주시 용담1동", "items": []}, ["holidays"])}
    assert verify("제주시 용담1동 와이파이에서 이상 구간 1개가 확인됐습니다 [R1].", r).ok
    assert not verify("제주시 용담1동 와이파이에서 이상 구간 1개가 확인됐습니다 [R3].", r).ok


def _doc_result(text):
    return {"R1": ToolResult("R1", "search_docs", {"query": "q"},
                             {"query": "q", "passages": [{"title": "명세서", "locator": "시트 A", "text": text}]}, ["시트 A"])}


def test_korean_date_quoted_from_document_passes():
    """문서 원문은 날짜를 '2019년 12월 31일'처럼 쓴다. 그대로 인용한 답변이 막히면 안 된다."""
    res = _doc_result("- 기간: 2019년 12월 31일 기준 - 본 데이터는 가공 형태로만 반출 가능합니다.")
    assert verify("명세서: 기간: 2019년 12월 31일 기준 [R1]", res).ok


def test_korean_date_not_in_document_fails():
    res = _doc_result("- 기간: 2019년 12월 31일 기준")
    v = verify("명세서: 기간: 2019년 12월 30일 기준 [R1]", res)
    assert not v.ok and "12월 30일" in v.errors[0]
