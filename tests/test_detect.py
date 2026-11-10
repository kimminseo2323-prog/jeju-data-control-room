import numpy as np
import pandas as pd
import pytest

from app.analytics.detect import Anomaly, detect_anomalies
from app.analytics.series import to_daily

METHODS = ["seasonal_z", "robust_resid"]


def weekly_series(days=140, seed=0, noise=20.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-10-01", periods=days, freq="D")
    weekly = np.array([1000, 980, 990, 1010, 1100, 1400, 1300])  # 화~월 패턴
    vals = weekly[np.arange(days) % 7] + rng.normal(0, noise, days)
    return pd.Series(vals, index=idx)


@pytest.mark.parametrize("method", METHODS)
def test_injected_spike_is_found_and_nothing_else(method):
    s = weekly_series()
    day = s.index[70]
    s[day] += 400  # 노이즈 표준편차의 20배
    found = detect_anomalies(s, method=method, threshold=3.5)
    assert [a.date for a in found] == [day]
    a = found[0]
    assert isinstance(a, Anomaly) and a.direction == "up" and a.expected < a.value


@pytest.mark.parametrize("method", METHODS)
def test_injected_drop_direction(method):
    s = weekly_series()
    day = s.index[90]
    s[day] -= 500
    found = detect_anomalies(s, method=method, threshold=3.5)
    assert [a.direction for a in found] == ["down"]


@pytest.mark.parametrize("method", METHODS)
def test_missing_days_are_not_anomalies(method):
    s = weekly_series()
    s[s.index[100:110]] = np.nan          # 데이터 공백
    s = s.drop(s.index[130:])             # 끝부분 미수록(데이터 지연)
    found = detect_anomalies(s, method=method, threshold=3.5)
    assert found == []


def test_to_daily_sums_and_keeps_gaps_as_nan():
    df = pd.DataFrame({"baseDate": ["20250101", "20250101", "20250103"], "emd": ["성산읍", "성산읍", "성산읍"],
                       "visitPop": [10, 5, 7]})
    s = to_daily(df, "baseDate", "visitPop", start="2025-01-01", end="2025-01-04")
    assert s.tolist()[:1] == [15]
    assert np.isnan(s["2025-01-02"]) and s["2025-01-03"] == 7 and np.isnan(s["2025-01-04"])


def test_to_daily_filters():
    df = pd.DataFrame({"baseDate": ["20250101", "20250101"], "emd": ["성산읍", "애월읍"], "visitPop": [10, 5]})
    s = to_daily(df, "baseDate", "visitPop", filters={"emd": "애월읍"})
    assert s.tolist() == [5]


def test_consecutive_anomalies_group_into_episodes():
    from app.analytics.detect import group_episodes
    d = pd.Timestamp("2024-07-26")
    mk = lambda k, pct, dirn="up": Anomaly(d + pd.Timedelta(days=k), 100 * (1 + pct), 100.0, 5.0 + k, dirn)
    anoms = [mk(0, 0.8), mk(1, 0.9), mk(2, 1.3), mk(3, 1.0), mk(10, 0.5), mk(12, -0.4, "down")]
    eps = group_episodes(anoms, max_gap=1)
    assert [(e.start.day, e.end.day, e.days, e.kind) for e in eps] == [
        (26, 29, 4, "지속 변화"), (5, 5, 1, "일시 급변"), (7, 7, 1, "일시 급변")]
    assert eps[0].peak.date == d + pd.Timedelta(days=3) and eps[0].peak.score == 8.0


def test_direction_change_splits_episode():
    from app.analytics.detect import group_episodes
    d = pd.Timestamp("2024-05-05")
    a = [Anomaly(d, 150, 100, 4, "up"), Anomaly(d + pd.Timedelta(days=1), 50, 100, -4, "down")]
    assert len(group_episodes(a)) == 2
