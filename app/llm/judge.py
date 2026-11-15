"""원인 후보 판정: 로컬 판단 모델(tev1, Ollama /v1/systemone) 기본, 연결이 안 되면 규칙 기반으로 대체.

판정 입력은 코드가 계산한 근거(이상 구간·맥락·동반 변화)뿐이며, 숫자를 새로 만들지 않는다.
보기별 확률을 그대로 '확신도'로 쓴다.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import requests

CAUSES = {
    "weather": "날씨(강한 비·바람·태풍 등)가 주된 원인이다.",
    "holiday": "공휴일·연휴가 주된 원인이다.",
    "event": "축제·행사가 주된 원인이다.",
    "tourism_demand": "관광 수요가 늘거나 줄어 같은 지역의 여러 신호가 함께 움직였다.",
    "season": "여러 날 이어진 변화로, 성수기·비수기 같은 계절적 전환이 주된 원인이다.",
    "data_issue": "실제 변화가 아니라 데이터 누락·집계 오류로 보인다.",
    "unknown": "주어진 근거로는 원인을 판단하기 어렵다.",
}
CAUSE_KO = {"weather": "날씨", "holiday": "공휴일·연휴", "event": "축제·행사", "tourism_demand": "관광 수요 변화", "season": "계절 전환(성수기·비수기)",
            "data_issue": "데이터 오류 의심", "unknown": "판단 불가"}
from app import config

config.load_env()
DEFAULT_HOST = os.getenv("JUDGE_HOST", "http://127.0.0.1:11434")   # Ollama 표준 포트. 다른 포트면 .env의 JUDGE_HOST
DEFAULT_MODEL = os.getenv("JUDGE_MODEL", "tev1:4b")
CONNECT_TIMEOUT = 1.0   # 서버가 없을 때 연결 거부를 기다리는 시간(초). 응답(판정) 대기 시간과 별개


@dataclass
class Judgment:
    choice: str
    probabilities: dict[str, float]
    confidence: float
    backend: str
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def level(self) -> str:
        p = self.probabilities.get(self.choice, 0)
        return "상" if p >= 0.7 else "중" if p >= 0.4 else "하"


def rule_judge(evidence: dict) -> Judgment:
    kinds = [c["kind"] for c in evidence.get("context", [])]
    co = evidence.get("co_movements", [])
    if "weather" in kinds:
        choice = "weather"
    elif "holiday" in kinds:
        choice = "holiday"
    elif "event" in kinds:
        choice = "event"
    elif len(co) >= 1:
        choice = "tourism_demand"
    elif evidence.get("anomaly", {}).get("kind") == "지속 변화" and _season_agrees(evidence):
        choice = "season"
    else:
        choice = "unknown"
    probs = {k: (0.75 if k == choice else 0.25 / (len(CAUSES) - 1)) for k in CAUSES}
    return Judgment(choice, probs, 0.5, "rule", "규칙: 기상 > 공휴일 > 행사 > 동반 변화 > 지속 변화가 성수기·비수기 방향과 같으면 계절 전환 > 판단 불가")


def _season_agrees(evidence: dict) -> bool:
    """지속 변화 방향(증가/감소)이 그 달 입도객 성수기(+)/비수기(-) 방향과 같은지."""
    pct = evidence.get("anomaly", {}).get("pct") or 0
    vals = [c.get("value") for c in evidence.get("context", []) if c.get("kind") == "visitors" and c.get("value") is not None]
    return any(v * pct > 0 for v in vals)


_MISSING = {"weather": "기상 특이사항 없음", "holiday": "공휴일 없음", "event": "지역이 확인된 행사 없음"}
NOT_COVERED_KO = {"weather": "기상", "event": "축제·행사", "visitors": "입도객"}
# 맥락 줄 앞에 근거 종류를 밝혀 보기(원인)와 연결하기 쉽게 한다(2026-11-11 대규모 평가에서 날씨 근거를 놓치는 경우가 많아 추가)
CONTEXT_KO = {"weather": "날씨·강한 비바람", "holiday": "공휴일", "event": "축제·행사", "visitors": "입도객 성수기·비수기",
              "recurrence": "작년 같은 시기"}


def evidence_text(evidence: dict) -> str:
    """판정 모델에 넘길 근거 문장. JSON을 그대로 넘기면 '제주 전체' 같은 근거의 뜻을 놓쳐(사전 실험) 문장으로 풀어 쓴다.
    숫자는 입력에 있는 값만 옮긴다."""
    a = evidence.get("anomaly", {})
    lines = [f"이상 신호: {a.get('emd', '')} {a.get('signal', '')} — {a.get('date', '')} 기준 {a.get('kind', '')}"
             f"({a.get('days', 1)}일), 평소(같은 요일 기준선) 대비 {float(a.get('pct', 0)):+.1f}%."]
    co = evidence.get("co_movements", [])
    if co:
        for c in co:
            word = "증가" if c.get("direction") == "up" else "감소"
            line = f"동반 변화: {c['signal']}도 {c['date']}에 평소보다 크게 움직였다(점수 {c['z']}, {word})."
            if str(c["signal"]).startswith("제주 전체"):
                line += " 즉 이 지역만의 변화가 아니라 섬 전체에서 함께 움직였다."
            elif str(c["signal"]).startswith("인근 읍면동"):
                line += " 즉 주변 지역도 함께 움직였다."
            lines.append(line)
    elif "co_checked" in evidence:   # 그날 자료가 있는 신호만 '평소 수준'이라 말한다
        if evidence["co_checked"]:
            lines.append(f"동반 변화 없음: 확인한 {', '.join(evidence['co_checked'])}는 평소 수준이었다.")
    else:
        lines.append("동반 변화 없음: 확인한 다른 신호와 제주 전체 합계는 평소 수준이었다.")
    if evidence.get("co_no_data"):
        lines.append(f"자료 없음: {', '.join(evidence['co_no_data'])}는 이 날짜 자료가 없어 함께 움직였는지 확인하지 못했다(변화가 없었다는 뜻이 아니다).")
    ctx = evidence.get("context", [])
    for c in ctx:
        label = CONTEXT_KO.get(c.get("kind"))
        lines.append(f"맥락({label}): {c['detail']}." if label else f"맥락: {c['detail']}.")
    kinds = {c.get("kind") for c in ctx}
    not_covered = set(evidence.get("not_covered", []))
    missing = [v for k, v in _MISSING.items() if k not in kinds and k not in not_covered]
    if missing:
        lines.append("맥락: " + ", ".join(missing) + ".")
    unchecked = [NOT_COVERED_KO[k] for k in evidence.get("not_covered", []) if k in NOT_COVERED_KO]
    if unchecked:
        lines.append(f"확인 불가: 이 날짜는 {'·'.join(unchecked)} 자료 제공 기간 밖이라 확인하지 못했다(없다는 뜻이 아니다).")
    return "\n".join(lines)


def judgment_label(j: Judgment) -> str:
    """화면에 보일 판정 한 줄. 규칙 판정은 확률이 없으므로(보기 확률은 고정값) 확률·확신도를 보이지 않는다."""
    if j.backend == "rule":
        return f"{CAUSE_KO[j.choice]} · 규칙으로 고른 후보(판단 모델 미연결, 확률 없음)"
    p = j.probabilities.get(j.choice, 0)
    return f"{CAUSE_KO[j.choice]} · 확신도 {j.level} ({p:.0%}) · 판단 모델 {j.backend}"


def model_status(http=requests, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL) -> tuple[bool, str]:
    """판단 모델을 실제로 쓸 수 있는지: 그 주소가 Ollama이고 모델이 설치되어 있어야 '연결됨'."""
    try:
        r = http.get(f"{host}/api/tags", timeout=(CONNECT_TIMEOUT, 5))
        r.raise_for_status()
        names = {m.get("name") for m in r.json().get("models", [])}
    except Exception:
        return False, "연결 안 됨 → 규칙 기반 판정"
    if model in names:
        return True, f"연결됨 · {model} (로컬)"
    return False, f"{model} 모델이 설치되지 않음(ollama pull {model}) → 규칙 기반 판정"


_VERIFIED: dict[tuple[str, str], tuple[float, bool]] = {}
VERIFY_TTL = 60.0   # 초. 실제 requests를 쓸 때만 확인 결과를 잠시 기억한다


def local_model_ready(http=requests, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL) -> bool:
    """그 주소가 판단 모델(tev1)이 설치된 Ollama인지(모델 목록에 있는지). 아니면 질문·근거를 보내지 않는다.
    기본 포트(11434)에 Ollama가 아닌 다른 프로그램이 떠 있는 PC가 있었다(2026-11-12 설치 재현 중 확인)."""
    if http is not requests:
        return model_status(http, host, model)[0]
    hit, now = _VERIFIED.get((host, model)), time.monotonic()
    if hit and now - hit[0] < VERIFY_TTL:
        return hit[1]
    ok = model_status(http, host, model)[0]
    _VERIFIED[(host, model)] = (now, ok)
    return ok


def judge_cause(evidence: dict, http=requests, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL, timeout: int = 120) -> Judgment:
    if not local_model_ready(http, host, model):
        j = rule_judge(evidence)
        j.note = f"로컬 판단 모델({model})을 확인하지 못함(연결 안 됨 또는 다른 프로그램) → 근거를 보내지 않고 규칙 기반으로 판정"
        return j
    body = {"model": model, "state": evidence_text(evidence), "questions": {"cause": {
        "type": "choice",
        "instructions": "Which listed cause best explains this anomaly in Jeju tourism/transport data? Judge only from the given evidence.",
        "criteria": CAUSES}}}
    try:
        r = http.post(f"{host}/v1/systemone", json=body, timeout=(CONNECT_TIMEOUT, timeout))
        r.raise_for_status()
        ans = r.json().get("answers", {}).get("cause", {})
        if ans.get("choice") not in CAUSES:
            raise ValueError(f"unexpected answer {ans}")
        return Judgment(ans["choice"], {k: float(v) for k, v in ans.get("probabilities", {}).items()},
                        float(ans.get("confidence", 0.0)), model)
    except Exception as e:  # 모델 미설치·서버 꺼짐·응답 이상 → 규칙 기반
        j = rule_judge(evidence)
        j.note = f"로컬 판단 모델 연결 실패({type(e).__name__}) → 규칙 기반으로 판정"
        return j
