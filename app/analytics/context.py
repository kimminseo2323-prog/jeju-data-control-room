"""이상일의 원인 후보 대조: 같은 날 다른 신호의 동반 변화 + 기상·공휴일·행사.

여기서 나오는 것은 '원인 후보'의 근거일 뿐 인과가 아니다. 판단 기준(강수·풍속 임계값)은 문서화된 상수로 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass

import holidays
import pandas as pd

from app.analytics.detect import score_series

RAIN_MM = 30.0     # 일강수량 기준(본 서비스 임의 기준, 기상특보 기준 아님)
WIND_MS = 14.0     # 최대풍속 기준(본 서비스 임의 기준)
KR_HOLIDAYS = holidays.country_holidays("KR", years=range(2015, 2031), language="ko")


@dataclass(frozen=True)
class CoMove:
    signal: str
    date: pd.Timestamp
    z: float
    direction: str


@dataclass(frozen=True)
class ContextItem:
    kind: str     # weather | holiday | event | visitors
    detail: str
    source: str


def find_co_movements(day: pd.Timestamp, signals: dict[str, pd.Series], threshold: float = 3.0,
                      window: int = 0, method: str = "seasonal_z") -> list[CoMove]:
    out = []
    days = [day + pd.Timedelta(days=k) for k in range(-window, window + 1)]
    for name, s in signals.items():
        scored = score_series(s, method)
        if scored is None:
            continue
        _, _, z = scored
        hits = [(d, z.get(d)) for d in days if pd.notna(z.get(d)) and abs(z.get(d)) >= threshold]
        if hits:
            d, v = max(hits, key=lambda h: abs(h[1]))
            out.append(CoMove(name, d, float(v), "up" if v > 0 else "down"))
    return out


def check_context(day: pd.Timestamp, emd: str, weather: pd.DataFrame | None = None,
                  station_of_emd: dict | None = None, events: pd.DataFrame | None = None) -> list[ContextItem]:
    items: list[ContextItem] = []
    day = pd.Timestamp(day).normalize()

    if weather is not None and station_of_emd and emd in station_of_emd:
        st = station_of_emd[emd]
        w = weather[(weather["station"] == st) & (pd.to_datetime(weather["date"]) == day)]
        for _, r in w.iterrows():
            parts = []
            if pd.notna(r.get("rain_mm")) and r["rain_mm"] >= RAIN_MM:
                parts.append(f"일강수량 {r['rain_mm']:.0f}mm")
            if pd.notna(r.get("wind_max")) and r["wind_max"] >= WIND_MS:
                parts.append(f"최대풍속 {r['wind_max']:.1f}m/s")
            if parts:
                items.append(ContextItem("weather", f"{st} 관측소 " + ", ".join(parts),
                                         "제주데이터허브 일별 기상 정보(579)"))

    for k in (-1, 0, 1):
        d = (day + pd.Timedelta(days=k)).date()
        if d in KR_HOLIDAYS:
            rel = {-1: "전날", 0: "당일", 1: "다음날"}[k]
            items.append(ContextItem("holiday", f"{KR_HOLIDAYS[d]} ({rel}, {d.isoformat()})",
                                     "holidays 오픈소스 패키지(대한민국 공휴일)"))

    if events is not None and len(events):
        ev = events[(events["start"] <= day) & (events["end"] >= day) & ((events["emd"] == emd) | events["emd"].isna())]
        for _, r in ev.iterrows():
            items.append(ContextItem("event", f"{r['name']} ({r['start']:%Y-%m-%d}~{r['end']:%Y-%m-%d})",
                                     "VISIT JEJU 축제행사콘텐츠(761), 지역은 수작업 지정"))
    return items
