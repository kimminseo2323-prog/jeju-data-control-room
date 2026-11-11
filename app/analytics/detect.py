"""일 단위 시계열 이상 탐지 — 두 방법을 같은 인터페이스로 제공.

seasonal_z  : 같은 요일 앞뒤 4주 값의 중앙값을 기대값으로, 잔차를 MAD로 표준화
robust_resid: STL(주기 7, robust) 분해 잔차를 MAD로 표준화. 결측일은 보간해 적합만 하고 판정에서는 제외
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

MAD_K = 1.4826


@dataclass(frozen=True)
class Anomaly:
    date: pd.Timestamp
    value: float
    expected: float
    score: float
    direction: str  # "up" | "down"

    @property
    def pct(self) -> float:
        return (self.value / self.expected - 1.0) if self.expected else float("nan")


def _robust_scale(resid: pd.Series) -> float:
    r = resid.dropna()
    mad = float(np.median(np.abs(r - np.median(r)))) * MAD_K if len(r) else 0.0
    return mad if mad > 0 else float(r.std() or 1.0)


def _expected_seasonal(s: pd.Series, weeks: int = 4, min_obs: int = 3) -> pd.Series:
    """같은 요일 앞뒤 weeks주 값(자기 자신 제외)의 중앙값. 이웃 관측이 min_obs개 미만이면 NaN.
    날짜 기준으로 맞춰(빈 날은 NaN) 7일 간격 이동을 한 번에 계산한다 — 날짜마다 반복하던 방식과 같은 값."""
    daily = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D")) if len(s) else s
    shifts = [daily.shift(-7 * k).to_numpy(dtype=float) for k in range(-weeks, weeks + 1) if k != 0]
    m = np.column_stack(shifts) if shifts else np.empty((len(daily), 0))
    n = np.sum(~np.isnan(m), axis=1)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # 이웃이 전부 NaN인 날의 nanmedian 경고
        med = np.nanmedian(m, axis=1) if m.shape[1] else np.full(len(daily), np.nan)
    out = pd.Series(np.where(n >= min_obs, med, np.nan), index=daily.index)
    return out.reindex(s.index)


def _expected_stl(s: pd.Series) -> pd.Series:
    filled = s.interpolate(limit_direction="both")
    # seasonal=13, trend=29(약 4주): 2주 이내의 짧은 변화를 이상으로 남기고, 잔차가 노이즈 크기를 과소추정하지 않도록 함
    res = STL(filled, period=7, seasonal=13, trend=29, robust=True).fit()
    return res.trend + res.seasonal


def score_series(s: pd.Series, method: Literal["seasonal_z", "robust_resid"] = "seasonal_z"):
    """(정리된 시계열, 기대값, 표준화 점수). 관측이 28일 미만이면 None."""
    s = s.astype(float).asfreq("D")
    if s.dropna().shape[0] < 28:
        return None
    expected = _expected_seasonal(s) if method == "seasonal_z" else _expected_stl(s)
    resid = (s - expected).where(s.notna())
    return s, expected, resid / _robust_scale(resid)


def detect_anomalies(s: pd.Series, method: Literal["seasonal_z", "robust_resid"] = "seasonal_z",
                     threshold: float = 3.0) -> list[Anomaly]:
    scored = score_series(s, method)
    if scored is None:
        return []
    s, expected, z = scored
    out = []
    for t, score in z.dropna().items():
        if abs(score) >= threshold:
            out.append(Anomaly(t, float(s[t]), float(expected[t]), float(score), "up" if score > 0 else "down"))
    return out


@dataclass(frozen=True)
class Episode:
    """연속된 같은 방향 이상일 묶음. 3일 이상이면 '지속 변화'(성수기 전환 등), 그 미만은 '일시 급변'."""
    start: pd.Timestamp
    end: pd.Timestamp
    days: int
    direction: str
    peak: Anomaly

    @property
    def kind(self) -> str:
        return "지속 변화" if self.days >= 3 else "일시 급변"


def group_episodes(anoms: list[Anomaly], max_gap: int = 1) -> list[Episode]:
    out: list[Episode] = []
    cur: list[Anomaly] = []
    for a in sorted(anoms, key=lambda x: x.date):
        if cur and (a.direction != cur[-1].direction or (a.date - cur[-1].date).days > max_gap):
            out.append(_episode(cur)); cur = []
        cur.append(a)
    if cur:
        out.append(_episode(cur))
    return out


def _episode(items: list[Anomaly]) -> Episode:
    peak = max(items, key=lambda x: abs(x.score))
    return Episode(items[0].date, items[-1].date, len(items), items[0].direction, peak)
