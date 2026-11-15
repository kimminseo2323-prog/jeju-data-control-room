"""관제판(기간 브리핑) 계산: 기간 선택, 기간 안의 주요 이상, 날짜별 이상 읍면동 수, 읍면동별 요약, 빠른 원인 후보.

화면(app/ui/app.py)은 이 결과를 배치만 한다. 빠른 원인 후보는 판정 모델 없이 규칙으로 정한 값이며(관제판을 빨리 띄우기 위해),
판정 모델(tev1)의 판정은 상세 분석 탭에서 실행한다.
"""
from __future__ import annotations

import re

import pandas as pd

from app.llm.judge import CAUSE_KO, NOT_COVERED_KO, rule_judge


def months(z: pd.DataFrame) -> list[str]:
    """값이 하나라도 있는 달('YYYY-MM'), 최근 달부터."""
    has = z.notna().any(axis=0)
    cols = pd.DatetimeIndex(z.columns[has.to_numpy()])
    return sorted({f"{d:%Y-%m}" for d in cols}, reverse=True)


def month_bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(month + "-01")
    return start, start + pd.offsets.MonthEnd(0)


def _window(z: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    cols = pd.DatetimeIndex(z.columns)
    return z.loc[:, (cols >= start) & (cols <= end)]


def daily_alarm_counts(z: pd.DataFrame, threshold: float, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """날짜별 이상(점수 절댓값이 기준 이상) 읍면동 수. 수집 안 된 칸은 세지 않는다."""
    w = _window(z, start, end)
    c = (w.abs() >= threshold).sum(axis=0)
    c.index = pd.DatetimeIndex(c.index)
    return c


def region_summary(z: pd.DataFrame, threshold: float, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """읍면동별 기간 안의 가장 큰 점수(부호 유지)와 이상일 수."""
    w = _window(z, start, end)
    idx = w.abs().fillna(-1).to_numpy().argmax(axis=1)
    peak = [w.iloc[i, j] if w.shape[1] else float("nan") for i, j in enumerate(idx)]
    return pd.DataFrame({"peak_z": peak, "alarm_days": (w.abs() >= threshold).sum(axis=1)}, index=w.index)


def period_episodes(ep: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """가장 큰 날이 기간 안에 있는 이상 구간, 점수(절댓값) 큰 순."""
    if ep.empty:
        return ep
    peak = pd.to_datetime(ep["최대일"])
    out = ep[(peak >= start) & (peak <= end)]
    return out.reindex(out["점수"].abs().sort_values(ascending=False).index)


def quick_cause(tb, signal: str, emd: str, day: str, direction: str) -> dict:
    """도구(동반 변화·맥락)와 규칙 판정으로 원인 후보와 근거 한 줄을 만든다. 판정 모델은 쓰지 않는다."""
    cr = tb.dispatch("find_co_movements", {"date": day, "emd": emd, "window": 1, "exclude_signal": signal}, "R1").data
    co = cr["co_movements"]
    cx = tb.dispatch("check_context", {"date": day, "emd": emd, "signal": signal}, "R2").data
    same = [c for c in cx["items"]
            if not (c["kind"] == "visitors" and c.get("value") is not None and (c["value"] > 0) != (direction == "up"))]
    ev = {"anomaly": {"emd": emd, "signal": signal, "date": day, "pct": 1 if direction == "up" else -1, "kind": ""},
          "context": same, "co_movements": co}
    cause = CAUSE_KO[rule_judge(ev).choice]
    order = {"weather": 0, "holiday": 1, "event": 2, "recurrence": 3, "visitors": 4}
    points = [short_point(c["detail"]) for c in sorted(same, key=lambda c: order.get(c["kind"], 9))][:1]
    if co:
        word = "증가" if co[0]["direction"] == "up" else "감소"
        points.append(f"{co[0]['signal']}도 함께 {word}" + (f" 외 {len(co) - 1}건" if len(co) > 1 else ""))
    if not points:   # 그날 비교할 다른 신호 자료가 하나도 없으면 '동반 변화 없음'이라 하지 않는다
        points.append("같은 날 확인된 맥락·동반 변화 없음" if cr.get("checked") else "같은 날 확인된 맥락 없음, 비교할 다른 신호 자료 없음")
    unchecked = ("·".join(NOT_COVERED_KO.get(k, k) for k in cx["not_covered"]) + " 확인 불가") if cx.get("not_covered") else ""
    return {"cause": cause, "points": points, "unchecked": unchecked, "reason": " / ".join(points + ([unchecked] if unchecked else []))}


def short_point(detail: str) -> str:
    """관제판 한 줄용으로 맥락 문장을 줄인다: 점수 괄호와 '…일 수 있음' 꼬리를 뗀다(상세 탭에는 원문 그대로)."""
    return re.sub(r"\(점수 [^)]*\)", "", detail).split(", 매년 반복")[0].strip()
