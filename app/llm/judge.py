"""원인 후보 판정: 로컬 판단 모델(tev1, Ollama /v1/systemone) 기본, 연결이 안 되면 규칙 기반으로 대체.

판정 입력은 코드가 계산한 근거(이상 구간·맥락·동반 변화)뿐이며, 숫자를 새로 만들지 않는다.
보기별 확률을 그대로 '확신도'로 쓴다.
"""
from __future__ import annotations

import json
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
    elif evidence.get("anomaly", {}).get("kind") == "지속 변화":
        choice = "season"
    else:
        choice = "unknown"
    probs = {k: (0.75 if k == choice else 0.25 / (len(CAUSES) - 1)) for k in CAUSES}
    return Judgment(choice, probs, 0.5, "rule", "규칙: 기상 > 공휴일 > 행사 > 동반 변화 > 지속 변화면 계절 전환 > 판단 불가")


def _state_text(evidence: dict) -> str:
    return json.dumps(evidence, ensure_ascii=False)


def judge_cause(evidence: dict, http=requests, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL, timeout: int = 120) -> Judgment:
    body = {"model": model, "state": _state_text(evidence), "questions": {"cause": {
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
