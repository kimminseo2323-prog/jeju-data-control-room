"""Agent 도구: 스키마(LLM에 보여줄 설명)와 실행. 모든 결과는 ToolResult(id, data, sources)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

from app.analytics.context import check_context, find_co_movements
from app.analytics.detect import detect_anomalies

SIGNAL_SOURCES = {
    "유동인구": "제주데이터허브 읍면동 단위 내국인 유동인구(583), 방문인구(visitPop) 합계",
    "와이파이": "제주데이터허브 와이파이 AP그룹별 일일 사용량(593), 이용자수 합계(AP→읍면동 매핑)",
    "버스": "제주데이터허브 일일 정류소별 버스 이용자 정보(613), 승차·일반·카드 합계(정류소→읍면동 매핑)",
}


@dataclass
class ToolResult:
    id: str
    tool: str
    args: dict
    data: Any
    sources: list[str] = field(default_factory=list)

    def for_llm(self) -> str:
        return json.dumps({"result_id": self.id, "data": self.data, "sources": self.sources}, ensure_ascii=False, default=str)


class ToolError(Exception):
    pass


class DataStore(Protocol):
    def series(self, signal: str, emd: str) -> pd.Series: ...
    def signals(self) -> list[str]: ...


class MemoryStore:
    def __init__(self, series: dict[tuple[str, str], pd.Series], weather=None, station_of_emd=None, events=None):
        self._series = series
        self.weather, self.station_of_emd, self.events = weather, station_of_emd, events

    def signals(self) -> list[str]:
        return sorted({k[0] for k in self._series})

    def series(self, signal: str, emd: str) -> pd.Series:
        if (signal, emd) not in self._series:
            raise ToolError(f"no data for signal={signal!r} emd={emd!r}; available signals={self.signals()}")
        return self._series[(signal, emd)]


def _period(s: pd.Series, start: str | None, end: str | None) -> pd.Series:
    return s.loc[pd.Timestamp(start) if start else None: pd.Timestamp(end) if end else None]


class Toolbox:
    def __init__(self, store: DataStore, index):
        self.store, self.index = store, index

    def specs(self) -> list[dict]:
        sig = {"type": "string", "enum": ["유동인구", "와이파이", "버스"], "description": "신호 종류"}
        emd = {"type": "string", "description": "읍면동, 예: '서귀포시 성산읍'"}
        date = {"type": "string", "description": "YYYY-MM-DD"}
        return [
            {"name": "get_series", "description": "읍면동의 일 단위 신호 값을 조회한다(요약 통계와 최근 값).",
             "parameters": {"type": "object", "properties": {"signal": sig, "emd": emd, "start": date, "end": date}, "required": ["signal", "emd"]}},
            {"name": "detect_anomalies", "description": "평소(요일 패턴 기준선)와 크게 다른 날을 찾는다.",
             "parameters": {"type": "object", "properties": {"signal": sig, "emd": emd, "start": date, "end": date,
                            "method": {"type": "string", "enum": ["seasonal_z", "robust_resid"]}, "threshold": {"type": "number"}}, "required": ["signal", "emd"]}},
            {"name": "find_co_movements", "description": "특정 날짜에 같은 읍면동의 다른 신호도 함께 크게 움직였는지 확인한다.",
             "parameters": {"type": "object", "properties": {"date": date, "emd": emd, "window": {"type": "integer"}}, "required": ["date", "emd"]}},
            {"name": "check_context", "description": "특정 날짜·읍면동의 기상, 공휴일, 행사 정보를 확인한다.",
             "parameters": {"type": "object", "properties": {"date": date, "emd": emd}, "required": ["date", "emd"]}},
            {"name": "search_docs", "description": "데이터 명세·API 문서·반출 기준·게시판 답변에서 관련 내용을 검색한다(출처 포함).",
             "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}}, "required": ["query"]}},
        ]

    def dispatch(self, name: str, args: dict, result_id: str) -> ToolResult:
        fn = getattr(self, f"_t_{name}", None)
        if fn is None or name not in {s["name"] for s in self.specs()}:
            raise ToolError(f"unknown tool {name!r}")
        try:
            data, sources = fn(**args)
        except TypeError as e:
            raise ToolError(f"bad arguments for {name}: {e}") from e
        return ToolResult(result_id, name, args, data, sources)

    # ---- tools ----
    def _t_get_series(self, signal, emd, start=None, end=None):
        s = _period(self.store.series(signal, emd), start, end)
        obs = s.dropna()
        data = {"signal": signal, "emd": emd, "first_date": str(s.index.min().date()) if len(s) else None,
                "last_date": str(obs.index.max().date()) if len(obs) else None, "days": int(len(s)),
                "missing_days": int(s.isna().sum()), "mean": round(float(obs.mean()), 1) if len(obs) else None,
                "recent": {str(k.date()): round(float(v), 1) for k, v in obs.tail(7).items()}}
        return data, [SIGNAL_SOURCES.get(signal, signal)]

    def _t_detect_anomalies(self, signal, emd, start=None, end=None, method="seasonal_z", threshold=3.0):
        s = _period(self.store.series(signal, emd), start, end)
        found = detect_anomalies(s, method=method, threshold=float(threshold))
        rows = [{"date": str(a.date.date()), "value": round(a.value, 1), "expected": round(a.expected, 1),
                 "pct": round(a.pct * 100, 1), "score": round(a.score, 2), "direction": a.direction} for a in found]
        return {"signal": signal, "emd": emd, "method": method, "threshold": threshold, "count": len(rows), "anomalies": rows}, [SIGNAL_SOURCES.get(signal, signal)]

    def _t_find_co_movements(self, date, emd, window=0):
        sigs = {}
        for name in self.store.signals():
            try:
                sigs[name] = self.store.series(name, emd)
            except ToolError:
                continue
        moves = find_co_movements(pd.Timestamp(date), sigs, threshold=3.0, window=int(window))
        rows = [{"signal": m.signal, "date": str(m.date.date()), "z": round(m.z, 2), "direction": m.direction} for m in moves]
        return {"date": date, "emd": emd, "checked": sorted(sigs), "co_movements": rows}, [SIGNAL_SOURCES[k] for k in sorted(sigs) if k in SIGNAL_SOURCES]

    def _t_check_context(self, date, emd):
        items = check_context(pd.Timestamp(date), emd, weather=getattr(self.store, "weather", None),
                              station_of_emd=getattr(self.store, "station_of_emd", None), events=getattr(self.store, "events", None))
        return {"date": date, "emd": emd, "items": [{"kind": i.kind, "detail": i.detail} for i in items]}, sorted({i.source for i in items})

    def _t_search_docs(self, query, k=5):
        hits = self.index.search(query, k=int(k))
        return {"query": query, "passages": [{"title": h.title, "locator": h.locator, "text": h.text[:600]} for h in hits]}, [h.locator for h in hits]
