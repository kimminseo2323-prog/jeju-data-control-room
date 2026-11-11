"""브리핑 검증기.

규칙
1. 숫자가 있는 문장은 [Rn] 근거를 달아야 한다.
2. 문장의 숫자는 인용한 결과(data) 안의 숫자와 일치해야 한다(소수로 쓰면 ±0.05, 정수로 쓰면 반올림값과 같아야 함).
   날짜(2025-01-29, 1월 29일)는 조각내지 않고 통째로 결과 안에 있는지 확인한다.
3. 인용한 결과 id가 실제로 있어야 한다.
4. '원인' 주장은 맥락(check_context) 또는 동반 변화(find_co_movements) 결과를 근거로 달아야 한다.
5. '때문이다/때문입니다' 같은 단정 표현은 경고.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from app.agent.tools import ToolResult

CITE = re.compile(r"\[(R\d+)\]")
NUM = re.compile(r"(?<![가-힣A-Za-z\d.])-?\d[\d,]*(?:\.\d+)?")
CAUSE_TOOLS = {"check_context", "find_co_movements"}
DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?:-(\d{2}))?(?!\d)")      # 2025-01-29, 2024-10
KDATE = re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")          # 1월 29일
ASSERTIVE = re.compile(r"때문(이다|입니다|이에요)|원인은 .*(이다|입니다)\.?$")


@dataclass
class VerifyResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _numbers_in(obj) -> list[float]:
    s = _dump(obj)
    # 날짜는 통째로 따로 확인하므로 숫자 후보에서 뺀다(연도만 남김) — 월·일 조각이 다른 숫자와 우연히 맞는 것을 막는다
    out = [float(y) for y, _, _ in DATE.findall(s)]
    s = DATE.sub(" ", s)
    # 문서 속 '1,000' 같은 천 단위 구분 숫자는 1000으로 읽는다
    for m in re.findall(r"(?<!\d)-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d)|(?<!\d)-?\d+(?:\.\d+)?", s):
        try:
            x = float(m.replace(",", ""))
            out.append(x)
            if x < 0:   # 감소는 문장에서 '48.2% 적었습니다'처럼 크기로 쓴다(방향은 말로 표현)
                out.append(-x)
        except ValueError:
            pass
    return out


def _matches(raw: str, pool: list[float]) -> bool:
    """소수로 쓴 숫자(35.4, 7.0)는 ±0.05, 정수로 쓴 숫자(1,354)는 결과값을 반올림(0.5는 올림)한 값과 같아야 한다."""
    x = float(raw.replace(",", ""))
    if "." in raw:
        return any(abs(x - y) <= 0.05 for y in pool)
    return any(x == math.floor(y + 0.5) for y in pool)


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
            dumps = " ".join(_dump(results[c].data) for c in cites)
            for d in DATE.finditer(body):
                if d.group() not in dumps:
                    errors.append(f"근거에 없는 날짜 {d.group()} ({', '.join(cites)}): {sent}")
            for d in KDATE.finditer(body):
                if f"-{int(d[1]):02d}-{int(d[2]):02d}" not in dumps:
                    errors.append(f"근거에 없는 날짜 {d.group()} ({', '.join(cites)}): {sent}")
            rest = KDATE.sub(" ", DATE.sub(lambda m: f" {m[1]} ", body))   # 날짜는 위에서 확인, 연도만 숫자로 남김
            pool = [n for c in cites for n in _numbers_in(results[c].data)]
            for raw in NUM.findall(rest):
                if not _matches(raw, pool):
                    errors.append(f"근거와 다른 숫자 {raw} ({', '.join(cites)}): {sent}")
        if "원인" in body or "때문" in body:
            if not any(results[c].tool in CAUSE_TOOLS for c in cites):
                errors.append(f"원인 주장에 맥락·동반 변화 근거가 없음: {sent}")
        if ASSERTIVE.search(body.strip()):
            warnings.append(f"단정 표현(원인 후보로 표현 권장): {sent}")
    return VerifyResult(ok=not errors, errors=errors, warnings=warnings)
