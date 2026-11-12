import numpy as np
import pandas as pd

from app.agent.tools import MemoryStore, Toolbox
from app.report.board import daily_alarm_counts, months, period_episodes, quick_cause, region_summary


def _z():
    idx = pd.date_range("2025-07-01", "2025-08-31", freq="D")
    z = pd.DataFrame(0.0, index=["제주시 이호동", "서귀포시 성산읍", "제주시 우도면"], columns=idx)
    z.loc["제주시 이호동", pd.Timestamp("2025-08-01")] = 5.0
    z.loc["서귀포시 성산읍", pd.Timestamp("2025-08-01")] = -4.0
    z.loc["서귀포시 성산읍", pd.Timestamp("2025-08-10")] = 3.6
    z.loc["제주시 우도면", pd.Timestamp("2025-08-01")] = 2.0          # 기준 미달
    z.loc["제주시 우도면", pd.Timestamp("2025-07-05")] = np.nan       # 수집 안 된 날
    return z


def test_months_latest_first():
    assert months(_z()) == ["2025-08", "2025-07"]


def test_daily_alarm_counts_both_directions_in_period():
    c = daily_alarm_counts(_z(), 3.5, pd.Timestamp("2025-08-01"), pd.Timestamp("2025-08-31"))
    assert c[pd.Timestamp("2025-08-01")] == 2 and c[pd.Timestamp("2025-08-10")] == 1
    assert c.index.min() == pd.Timestamp("2025-08-01") and c.sum() == 3


def test_region_summary_keeps_signed_peak_and_alarm_days():
    r = region_summary(_z(), 3.5, pd.Timestamp("2025-08-01"), pd.Timestamp("2025-08-31"))
    assert r.loc["제주시 이호동", "peak_z"] == 5.0
    assert r.loc["서귀포시 성산읍", "peak_z"] == -4.0 and r.loc["서귀포시 성산읍", "alarm_days"] == 2
    assert r.loc["제주시 우도면", "alarm_days"] == 0


def test_period_episodes_filters_by_peak_day_and_sorts_by_score():
    ep = pd.DataFrame({"읍면동": ["a", "b", "c"], "최대일": [pd.Timestamp("2025-08-02").date(), pd.Timestamp("2025-08-20").date(),
                                                     pd.Timestamp("2025-07-30").date()], "점수": [4.0, -9.0, 20.0]})
    out = period_episodes(ep, pd.Timestamp("2025-08-01"), pd.Timestamp("2025-08-31"))
    assert list(out["읍면동"]) == ["b", "a"]


def test_quick_cause_names_holiday_with_reason():
    idx = pd.date_range("2024-07-01", "2024-12-31", freq="D")
    rng = np.random.default_rng(0)
    s = pd.Series(1000 + rng.normal(0, 20, len(idx)), index=idx)
    s[pd.Timestamp("2024-09-16")] += 900
    tb = Toolbox(MemoryStore(series={("유동인구", "서귀포시 성산읍"): s}), index=None)
    r = quick_cause(tb, "유동인구", "서귀포시 성산읍", "2024-09-16", "up")
    assert r["cause"] == "공휴일·연휴" and "추석" in r["reason"]


def test_quick_cause_without_evidence_says_unknown():
    idx = pd.date_range("2024-07-01", "2024-12-31", freq="D")
    rng = np.random.default_rng(1)
    s = pd.Series(1000 + rng.normal(0, 20, len(idx)), index=idx)
    s[pd.Timestamp("2024-10-23")] += 900   # 평일, 공휴일 아님
    tb = Toolbox(MemoryStore(series={("유동인구", "제주시 연동"): s}), index=None)
    r = quick_cause(tb, "유동인구", "제주시 연동", "2024-10-23", "up")
    assert r["cause"] == "판단 불가" and r["reason"]
