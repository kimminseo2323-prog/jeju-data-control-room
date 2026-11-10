"""브리핑 검증기.

규칙
1. 숫자가 있는 문장은 [Rn] 근거를 달아야 한다.
2. 문장의 숫자는 인용한 결과(data) 안의 숫자와 일치해야 한다(소수 1자리 허용 오차, 정수 반올림 허용).
3. 인용한 결과 id가 실제로 있어야 한다.
4. '원인' 주장은 맥락(check_context) 또는 동반 변화(find_co_movements) 결과를 근거로 달아야 한다.
5. '때문이다/때문입니다' 같은 단정 표현은 경고.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.agent.tools import ToolResult

CITE = re.compile(r"\[(R\d+)\]")
NUM = re.compile(r"(?<![가-힣A-Za-z\d.])-?\d[\d,]*(?:\.\d+)?")
CAUSE_TOOLS = {"check_context", "find_co_movements"}
ASSERTIVE = re.compile(r"때문(이다|입니다|이에요)|원인은 .*(이다|입니다)\.?$")


@dataclass
class VerifyResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _numbers_in(obj) -> list[float]:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    out = []
    for m in re.findall(r"(?<!\d)-?\d+(?:\.\d+)?", s):  # 날짜 2025-01-29 → 2025, 01, 29
        try:
            out.append(float(m))
        except ValueError:
            pass
    return out


def _matches(x: float, pool: list[float]) -> bool:
    for y in pool:
        if abs(x - y) <= 0.05 or (float(x).is_integer() and abs(x - y) < 1):
            return True
    return False


def verify(text: str, results: dict[str, ToolResult]) -> VerifyResult:
    errors, warnings = [], []
    for sent in _sentences(text):
        cites = CITE.findall(sent)
        body = CITE.sub("", sent)
        nums = [m for m in NUM.findall(body)]
        missing = [c for c in cites if c not in results]
        if missing:
            errors.append(f"없는 근거 id {missing}: {sent}")
            continue
        if nums and not cites:
            errors.append(f"숫자에 근거([Rn])가 없음: {sent}")
            continue
        if nums:
            pool = [n for c in cites for n in _numbers_in(results[c].data)]
            for raw in nums:
                x = float(raw.replace(",", ""))
                if not _matches(x, pool):
                    errors.append(f"근거와 다른 숫자 {raw} ({', '.join(cites)}): {sent}")
        if "원인" in body or "때문" in body:
            if not any(results[c].tool in CAUSE_TOOLS for c in cites):
                errors.append(f"원인 주장에 맥락·동반 변화 근거가 없음: {sent}")
        if ASSERTIVE.search(body.strip()):
            warnings.append(f"단정 표현(원인 후보로 표현 권장): {sent}")
    return VerifyResult(ok=not errors, errors=errors, warnings=warnings)
