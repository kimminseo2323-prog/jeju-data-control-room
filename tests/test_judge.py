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


def test_default_host_is_standard_ollama_port_unless_configured(monkeypatch):
    import importlib
    import app.llm.judge as jm
    monkeypatch.delenv("JUDGE_HOST", raising=False)
    monkeypatch.setattr("app.config.load_env", lambda: None)
    assert importlib.reload(jm).DEFAULT_HOST == "http://127.0.0.1:11434"
    monkeypatch.setenv("JUDGE_HOST", "http://127.0.0.1:11500")
    assert importlib.reload(jm).DEFAULT_HOST == "http://127.0.0.1:11500"


class TagsHTTP:
    def __init__(self, payload=None, fail=False):
        self.payload, self.fail = payload, fail

    def get(self, url, timeout=None):
        if self.fail:
            raise ConnectionError("down")
        payload = self.payload

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return payload
        return R()


def test_model_status_requires_the_model_to_be_installed():
    from app.llm.judge import model_status
    assert model_status(TagsHTTP({"models": [{"name": "tev1:4b"}, {"name": "qwen:7b"}]}), model="tev1:4b")[0] is True
    ok, msg = model_status(TagsHTTP({"models": [{"name": "qwen:7b"}]}), model="tev1:4b")
    assert ok is False and "tev1:4b" in msg
    assert model_status(TagsHTTP({"version": "luna-shim-1"}), model="tev1:4b")[0] is False   # Ollama가 아닌 다른 프로그램
    assert model_status(TagsHTTP(fail=True), model="tev1:4b")[0] is False


class _RecordTimeout:
    def __init__(self):
        self.timeouts = []

    def post(self, url, json=None, timeout=None):
        self.timeouts.append(timeout)
        raise ConnectionError("refused")


def test_model_down_is_detected_within_a_second():
    """모델 서버가 없으면 Windows는 연결 거부까지 약 2초를 기다린다. 연결 대기는 1초 이하로, 응답 대기는 길게."""
    from app.agent.local import route
    from app.llm.judge import judge_cause
    h = _RecordTimeout()
    route("이호동 7월 28일에 왜?", http=h)
    judge_cause({"anomaly": {"emd": "제주시 이호동", "signal": "유동인구", "date": "2024-07-28", "pct": 50.0},
                 "context": [], "co_movements": []}, http=h)
    assert len(h.timeouts) == 2
    for t in h.timeouts:
        assert isinstance(t, tuple) and t[0] <= 1 and t[1] >= 60


def test_evidence_text_explains_neighbor_and_recurrence():
    from app.llm.judge import evidence_text
    t = evidence_text({"anomaly": {"emd": "제주시 이호동", "signal": "유동인구", "date": "2025-07-27", "pct": 80.0},
                       "co_movements": [{"signal": "인근 읍면동 유동인구", "date": "2025-07-27", "z": 5.1, "direction": "up"}],
                       "context": [{"kind": "recurrence", "detail": "작년 같은 시기(2024-07-28)에도 평소보다 많았음(점수 6.0)"}]})
    assert "주변 지역도 함께" in t
    assert "작년 같은 시기" in t


def test_evidence_text_says_unknown_not_absent_outside_source_period():
    from app.llm.judge import evidence_text
    t = evidence_text({"anomaly": {"emd": "제주시 이호동", "signal": "유동인구", "date": "2025-08-02", "pct": 50.0},
                       "co_movements": [], "context": [], "not_covered": ["weather", "event"]})
    assert "기상 특이사항 없음" not in t and "지역이 확인된 행사 없음" not in t
    assert "자료 제공 기간 밖" in t and "공휴일 없음" in t


def test_evidence_text_names_the_kind_of_each_context():
    """맥락 줄마다 어떤 종류의 근거인지(날씨·공휴일·축제·행사) 밝혀 보기(원인)와 연결하기 쉽게 한다."""
    from app.llm.judge import evidence_text
    t = evidence_text({"anomaly": {"emd": "제주시 아라동", "signal": "유동인구", "date": "2025-02-08", "pct": -32.5},
                       "co_movements": [], "context": [{"kind": "weather", "detail": "제주 관측소 일강수량 45mm"},
                                                        {"kind": "holiday", "detail": "설날 (당일, 2025-01-29)"}]})
    assert "맥락(날씨·강한 비바람): 제주 관측소 일강수량 45mm." in t
    assert "맥락(공휴일): 설날 (당일, 2025-01-29)." in t
