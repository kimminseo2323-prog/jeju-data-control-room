from app.llm.judge import CAUSES, evidence_text, judge_cause, rule_judge


EVID_HOLIDAY = {"anomaly": {"emd": "서귀포시 성산읍", "signal": "유동인구", "date": "2025-01-29", "pct": 35.4, "kind": "일시 급변"},
                "context": [{"kind": "holiday", "detail": "설날 (당일, 2025-01-29)"}], "co_movements": []}


def test_rule_judge_prefers_explicit_context():
    j = rule_judge(EVID_HOLIDAY)
    assert j.choice == "holiday" and j.backend == "rule" and abs(sum(j.probabilities.values()) - 1) < 1e-9


def test_rule_judge_co_movement_means_tourism_demand():
    ev = {**EVID_HOLIDAY, "context": [], "co_movements": [{"signal": "버스", "z": 4.0}, {"signal": "와이파이", "z": 3.6}]}
    assert rule_judge(ev).choice == "tourism_demand"


def test_rule_judge_nothing_is_unknown():
    assert rule_judge({**EVID_HOLIDAY, "context": []}).choice == "unknown"


class FakeHTTP:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, None

    def post(self, url, json=None, timeout=None):
        self.sent = (url, json)
        if not self.ok:
            raise ConnectionError("down")

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"answers": {"cause": {"choice": "holiday", "confidence": 0.9,
                                              "probabilities": {k: (0.9 if k == "holiday" else 0.02) for k in CAUSES}}}}
        return R()


def test_judge_uses_local_model_when_available():
    http = FakeHTTP()
    j = judge_cause(EVID_HOLIDAY, http=http)
    assert j.backend == "tev1:4b" and j.choice == "holiday" and j.confidence == 0.9
    url, body = http.sent
    assert url.endswith("/v1/systemone") and set(body["questions"]["cause"]["criteria"]) == set(CAUSES)


def test_judge_falls_back_to_rules_when_model_down():
    j = judge_cause(EVID_HOLIDAY, http=FakeHTTP(ok=False))
    assert j.backend == "rule" and j.choice == "holiday" and "연결" in j.note


def test_sustained_shift_without_visitor_evidence_is_unknown():
    ev = {"anomaly": {**EVID_HOLIDAY["anomaly"], "kind": "지속 변화", "days": 4}, "context": [], "co_movements": []}
    assert rule_judge(ev).choice == "unknown" and "season" in CAUSES


def _sustained(direction_pct, visitors_value=None):
    ctx = [] if visitors_value is None else [{"kind": "visitors", "detail": "입도객", "value": visitors_value}]
    return {"anomaly": {**EVID_HOLIDAY["anomaly"], "kind": "지속 변화", "days": 4, "pct": direction_pct},
            "context": ctx, "co_movements": []}


def test_sustained_rise_in_high_season_is_seasonal():
    assert rule_judge(_sustained(40.0, visitors_value=8.5)).choice == "season"


def test_sustained_rise_in_low_season_is_not_seasonal():
    assert rule_judge(_sustained(40.0, visitors_value=-12.0)).choice == "unknown"


def test_evidence_text_spells_out_island_wide_co_movement_and_missing_context():
    ev = {"anomaly": {"emd": "제주시 이호동", "signal": "유동인구", "date": "2024-07-29", "pct": 116.0, "kind": "지속 변화", "days": 4},
          "context": [], "co_movements": [{"signal": "제주 전체 유동인구", "date": "2024-07-30", "z": 8.42, "direction": "up"}]}
    t = evidence_text(ev)
    assert "제주시 이호동" in t and "+116.0%" in t and "4일" in t
    assert "제주 전체" in t and "섬 전체" in t
    assert "공휴일 없음" in t and "기상 특이사항 없음" in t and "행사 없음" in t


def test_evidence_text_lists_given_context():
    t = evidence_text(EVID_HOLIDAY)
    assert "설날" in t and "공휴일 없음" not in t and "동반 변화 없음" in t


def test_judge_sends_sentences_not_json():
    http = FakeHTTP()
    judge_cause(EVID_HOLIDAY, http=http)
    assert http.sent[1]["state"] == evidence_text(EVID_HOLIDAY)
