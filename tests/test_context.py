import datetime as dt

import numpy as np
import pandas as pd

from app.analytics.context import CoMove, ContextItem, check_context, find_co_movements
from tests.test_detect import weekly_series


def test_two_signals_jumping_together_are_both_reported():
    a, b, c = weekly_series(seed=1), weekly_series(seed=2), weekly_series(seed=3)
    day = a.index[60]
    a[day] += 400
    b[day] += 400
    moves = find_co_movements(day, {"유동인구": a, "버스": b, "와이파이": c}, threshold=3.5)
    assert sorted(m.signal for m in moves) == ["버스", "유동인구"]
    assert all(isinstance(m, CoMove) and m.direction == "up" for m in moves)


def test_co_movement_window_catches_next_day():
    a, b = weekly_series(seed=1), weekly_series(seed=2)
    day = a.index[60]
    b[a.index[61]] += 400
    assert [m.signal for m in find_co_movements(day, {"버스": b}, threshold=3.5, window=1)] == ["버스"]
    assert find_co_movements(day, {"버스": b}, threshold=3.5, window=0) == []


def _weather():
    return pd.DataFrame({"date": pd.to_datetime(["2024-07-10", "2024-07-11"]), "station": ["성산", "성산"],
                         "rain_mm": [85.0, 0.0], "wind_max": [9.0, 3.0]})


def test_heavy_rain_day_reports_weather():
    items = check_context(pd.Timestamp("2024-07-10"), "서귀포시 성산읍", weather=_weather(),
                          station_of_emd={"서귀포시 성산읍": "성산"})
    w = [i for i in items if i.kind == "weather"]
    assert len(w) == 1 and "85" in w[0].detail and w[0].source


def test_holiday_reported():
    items = check_context(pd.Timestamp("2025-01-29"), "서귀포시 성산읍")
    assert any(i.kind == "holiday" and "설" in i.detail for i in items)


def test_event_overlap_reported_only_for_matching_region():
    ev = pd.DataFrame({"name": ["성산일출축제", "탐라문화제"], "start": pd.to_datetime(["2024-12-30", "2024-10-01"]),
                       "end": pd.to_datetime(["2025-01-01", "2024-10-05"]), "emd": ["서귀포시 성산읍", "제주시 건입동"]})
    items = check_context(pd.Timestamp("2024-12-31"), "서귀포시 성산읍", events=ev)
    assert [i.detail for i in items if i.kind == "event"] == ["성산일출축제 (2024-12-30~2025-01-01)"]


def test_quiet_day_has_no_context():
    assert check_context(pd.Timestamp("2024-07-11"), "서귀포시 성산읍", weather=_weather(),
                         station_of_emd={"서귀포시 성산읍": "성산"}) == []


def _monthly(peak_month="2024-08", peak=1.2, low_month="2025-02", low=0.8):
    idx = pd.date_range("2024-04-01", "2025-03-01", freq="MS")
    v = pd.Series(1_000_000.0, index=idx)
    v[pd.Timestamp(peak_month + "-01")] *= peak
    v[pd.Timestamp(low_month + "-01")] *= low
    return v


def test_peak_month_visitors_reported_as_high_season():
    items = check_context(pd.Timestamp("2024-08-15"), "제주시 이호동", visitors=_monthly())
    v = [i for i in items if i.kind == "visitors"]
    assert len(v) == 1 and v[0].value > 0 and "성수기" in v[0].detail and "2024-08" in v[0].detail and v[0].source


def test_low_month_visitors_reported_as_low_season():
    v = [i for i in check_context(pd.Timestamp("2025-02-10"), "제주시 이호동", visitors=_monthly()) if i.kind == "visitors"]
    assert len(v) == 1 and v[0].value < 0 and "비수기" in v[0].detail


def test_ordinary_month_visitors_not_reported():
    assert [i for i in check_context(pd.Timestamp("2024-05-10"), "제주시 이호동", visitors=_monthly()) if i.kind == "visitors"] == []


def test_month_without_visitor_data_not_reported():
    assert [i for i in check_context(pd.Timestamp("2026-01-10"), "제주시 이호동", visitors=_monthly()) if i.kind == "visitors"] == []


def test_foreign_signal_uses_visitor_country_holidays_not_korean():
    """외국인 신호: 한국 공휴일 앞뒤 급증은 평소의 1.1배뿐(일본인은 자국 공휴일 2.3배, 중국인 1.7배) → 중국·일본 공휴일을 근거로."""
    items = check_context(pd.Timestamp("2025-10-01"), "제주시 연동", holiday_countries=("CN", "JP"))
    hol = [i.detail for i in items if i.kind == "holiday"]
    assert any(d.startswith("중국 공휴일") for d in hol)
    assert not any("개천절" in d or "추석" in d for d in hol)   # 2025-10-03 개천절, 10-05~07 추석은 넣지 않음


def test_japanese_golden_week_reported_for_foreign_signal():
    items = check_context(pd.Timestamp("2025-05-04"), "제주시 연동", holiday_countries=("CN", "JP"))
    assert any(i.kind == "holiday" and i.detail.startswith("일본 공휴일") for i in items)


def test_default_is_korean_holidays():
    items = check_context(pd.Timestamp("2025-10-03"), "제주시 연동")
    assert any(i.kind == "holiday" and "개천절" in i.detail for i in items)
