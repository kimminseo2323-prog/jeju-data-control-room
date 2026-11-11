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


def _expected_seasonal_reference(s, weeks=4, min_obs=3):
    """최초 구현(날짜마다 반복). 빠른 구현이 같은 값을 내는지 대조하는 기준."""
    out = pd.Series(np.nan, index=s.index)
    for t in s.index:
        vals = s.reindex([t + pd.Timedelta(weeks=k) for k in range(-weeks, weeks + 1) if k != 0]).dropna()
        if len(vals) >= min_obs:
            out[t] = float(vals.median())
    return out


def test_seasonal_baseline_matches_reference_with_gaps():
    from app.analytics.detect import _expected_seasonal
    rng = np.random.default_rng(7)
    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    s = pd.Series(rng.normal(1000, 80, len(idx)), index=idx)
    s.iloc[rng.choice(400, 60, replace=False)] = np.nan   # 흩어진 결측
    s.iloc[100:130] = np.nan                               # 긴 결측(이웃이 3개 미만인 날 생김)
    got, ref = _expected_seasonal(s), _expected_seasonal_reference(s)
    pd.testing.assert_series_equal(got, ref, check_names=False, check_freq=False)
    assert ref.isna().sum() > 0   # 기준값이 없는 날도 대조됨


def test_seasonal_baseline_is_fast_enough_for_43_regions():
    """질문하기 '어디서 이상했나'는 43개 읍면동을 훑는다. 2년치 1개 지역 기준선이 0.05초 안이어야 센터 PC에서도 수 초 안."""
    import time
    from app.analytics.detect import _expected_seasonal
    s = pd.Series(np.arange(730, dtype=float), index=pd.date_range("2024-01-01", periods=730, freq="D"))
    t0 = time.perf_counter()
    _expected_seasonal(s)
    assert time.perf_counter() - t0 < 0.05
