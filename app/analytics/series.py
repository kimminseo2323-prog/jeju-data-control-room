"""캐시 데이터 → 일 단위 시계열. 수록되지 않은 날은 0이 아니라 NaN으로 남긴다(공백을 '급감'으로 오인하지 않기 위해)."""
from __future__ import annotations

import pandas as pd


def to_daily(df: pd.DataFrame, date_col: str, value_col: str, filters: dict | None = None,
             start: str | None = None, end: str | None = None) -> pd.Series:
    d = df
    for k, v in (filters or {}).items():
        d = d[d[k].isin(v) if isinstance(v, (list, tuple, set)) else d[k] == v]
    dates = pd.to_datetime(d[date_col].astype(str), format="%Y%m%d")
    s = pd.to_numeric(d[value_col], errors="coerce").groupby(dates).sum(min_count=1)
    if s.empty and not (start and end):
        return s.astype(float)
    lo = pd.Timestamp(start) if start else s.index.min()
    hi = pd.Timestamp(end) if end else s.index.max()
    return s.reindex(pd.date_range(lo, hi, freq="D")).astype(float)
