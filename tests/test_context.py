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
