from app.llm.judge import CAUSES, judge_cause, rule_judge


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


def test_sustained_shift_without_context_is_seasonal():
    ev = {"anomaly": {**EVID_HOLIDAY["anomaly"], "kind": "지속 변화", "days": 4}, "context": [], "co_movements": []}
    assert rule_judge(ev).choice == "season" and "season" in CAUSES
