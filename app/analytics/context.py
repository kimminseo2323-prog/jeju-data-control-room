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
SEASON_PCT = 5.0   # 월 입도객이 주변 12개월 평균보다 ±5% 이상이면 성수기/비수기로 표시(본 서비스 임의 기준)
KR_HOLIDAYS = holidays.country_holidays("KR", years=range(2015, 2031), language="ko")
# 외국인 신호용: 방문객 국가 공휴일. 2024-04~2026-08 읍면동 급증(점수 3.5 이상) 비율이 자국 공휴일 앞뒤에서
# 일본인 2.3배·중국인 1.7배인 반면 한국 공휴일 앞뒤에서는 외국인 전체 1.1배였다(노트북 06).
HOLIDAY_COUNTRY_KO = {"KR": "", "CN": "중국 공휴일", "JP": "일본 공휴일"}
_HOLIDAYS = {"KR": KR_HOLIDAYS,
             **{c: holidays.country_holidays(c, years=range(2015, 2031), language="en_US") for c in ("CN", "JP")}}


@dataclass(frozen=True)
class CoMove:
    signal: str
    date: pd.Timestamp
    z: float
    direction: str


@dataclass(frozen=True)
class ContextItem:
    kind: str     # weather | holiday | event | visitors | recurrence
    detail: str
    source: str
    value: float | None = None   # visitors: 주변 12개월 평균 대비 %(+ 성수기, - 비수기), recurrence: 작년 점수


RECUR_DAYS, RECUR_WINDOW, RECUR_Z = 364, 3, 3.0   # 52주 전(같은 요일) ±3일, 점수 3 이상이면 '작년에도 이상'


def recurrence(s: pd.Series, day: pd.Timestamp, signal: str = "", method: str = "seasonal_z") -> ContextItem | None:
    """작년 같은 시기(52주 전 ±3일)에도 같은 방향의 이상이 있었는지. 매년 반복되는 행사·연휴·계절 변화의 근거.
    올해 그날이 이상이 아니거나, 작년 자료가 없으면 None."""
    scored = score_series(s, method)
    if scored is None:
        return None
    _, _, z = scored
    day = pd.Timestamp(day).normalize()
    now = z.get(day)
    if now is None or pd.isna(now) or abs(now) < RECUR_Z:
        return None
    centre = day - pd.Timedelta(days=RECUR_DAYS)
    win = z.loc[centre - pd.Timedelta(days=RECUR_WINDOW): centre + pd.Timedelta(days=RECUR_WINDOW)].dropna()
    same = win[(win.abs() >= RECUR_Z) & ((win > 0) == (now > 0))]
    if same.empty:
        return None
    d = same.abs().idxmax()
    word = "많았음" if now > 0 else "적었음"
    return ContextItem("recurrence", f"작년 같은 시기({d:%Y-%m-%d})에도 {signal} 평소보다 {word}(점수 {float(same[d]):.2f}), 매년 반복되는 변화일 수 있음".replace("  ", " "),
                       "같은 데이터의 1년 전 값(52주 전 같은 요일 ±3일)", round(float(same[d]), 2))


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


def season_index(visitors: pd.Series, month: pd.Timestamp) -> float | None:
    """해당 월 입도객이 주변 12개월(앞 6개월~뒤 5개월, 있는 달만) 평균보다 몇 % 많은지."""
    month = pd.Timestamp(month).to_period("M").to_timestamp()
    if month not in visitors.index or pd.isna(visitors[month]):
        return None
    win = visitors[(visitors.index >= month - pd.DateOffset(months=6)) & (visitors.index <= month + pd.DateOffset(months=5))].dropna()
    if len(win) < 6:
        return None
    return float(visitors[month] / win.mean() * 100 - 100)


def check_context(day: pd.Timestamp, emd: str, weather: pd.DataFrame | None = None,
                  station_of_emd: dict | None = None, events: pd.DataFrame | None = None,
                  visitors: pd.Series | None = None, holiday_countries: tuple[str, ...] = ("KR",)) -> list[ContextItem]:
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

    for country in holiday_countries:
        cal, prefix = _HOLIDAYS[country], HOLIDAY_COUNTRY_KO[country]
        for k in (-1, 0, 1):
            d = (day + pd.Timedelta(days=k)).date()
            if d in cal:
                rel = {-1: "전날", 0: "당일", 1: "다음날"}[k]
                name = f"{prefix} {cal[d]}" if prefix else cal[d]
                items.append(ContextItem("holiday", f"{name} ({rel}, {d.isoformat()})",
                                         f"holidays 오픈소스 패키지({'대한민국' if country == 'KR' else prefix[:2]} 공휴일)"))

    if events is not None and len(events):
        ev = events[(events["start"] <= day) & (events["end"] >= day) & ((events["emd"] == emd) | events["emd"].isna())]
        for _, r in ev.iterrows():
            items.append(ContextItem("event", f"{r['name']} ({r['start']:%Y-%m-%d}~{r['end']:%Y-%m-%d})",
                                     "제주관광공사 VISIT JEJU 축제행사콘텐츠(허브 761), 지역은 행사명 속 지명으로 연결"))

    if visitors is not None and len(visitors):
        si = season_index(visitors, day)
        if si is not None and abs(si) >= SEASON_PCT:
            m = day.to_period("M").to_timestamp()
            label = "성수기" if si > 0 else "비수기"
            items.append(ContextItem("visitors", f"{m:%Y-%m} 입도객 {visitors[m] / 10000:.1f}만 명, 주변 12개월 평균 대비 {si:+.1f}%({label})",
                                     "제주데이터허브 방문목적별 입도객 현황(580), 월 합계", round(si, 1)))
    return items
