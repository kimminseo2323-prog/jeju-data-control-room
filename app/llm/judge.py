"""원인 후보 판정: 로컬 판단 모델(tev1, Ollama /v1/systemone) 기본, 연결이 안 되면 규칙 기반으로 대체.

판정 입력은 코드가 계산한 근거(이상 구간·맥락·동반 변화)뿐이며, 숫자를 새로 만들지 않는다.
보기별 확률을 그대로 '확신도'로 쓴다.
"""
from __future__ import annotations

import os
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
DEFAULT_HOST = os.getenv("JUDGE_HOST", "http://127.0.0.1:11500")
DEFAULT_MODEL = os.getenv("JUDGE_MODEL", "tev1:4b")


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


_MISSING = {"weather": "기상 특이사항 없음", "holiday": "공휴일 없음", "event": "등록된 행사 없음"}


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
            lines.append(line)
    else:
        lines.append("동반 변화 없음: 확인한 다른 신호와 제주 전체 합계는 평소 수준이었다.")
    ctx = evidence.get("context", [])
    for c in ctx:
        lines.append(f"맥락: {c['detail']}.")
    kinds = {c.get("kind") for c in ctx}
    missing = [v for k, v in _MISSING.items() if k not in kinds]
    if missing:
        lines.append("맥락: " + ", ".join(missing) + ".")
    return "\n".join(lines)


def judge_cause(evidence: dict, http=requests, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL, timeout: int = 120) -> Judgment:
    body = {"model": model, "state": evidence_text(evidence), "questions": {"cause": {
        "type": "choice",
        "instructions": "Which listed cause best explains this anomaly in Jeju tourism/transport data? Judge only from the given evidence.",
        "criteria": CAUSES}}}
    try:
        r = http.post(f"{host}/v1/systemone", json=body, timeout=timeout)
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
