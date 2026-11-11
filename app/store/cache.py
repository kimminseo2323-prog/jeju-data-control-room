"""수집 캐시(data/cache/*.parquet) → 읍면동별 일 단위 신호, 기상, 행사, 데이터 품질 지표."""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from app.agent.tools import ToolError
from app.analytics.series import to_daily
from app.store.geo import assign_emd, haversine_m, normalize_emd

SIGNALS = ["유동인구", "와이파이", "버스"]


class CacheStore:
    def __init__(self, cache_dir: Path | str, events: pd.DataFrame | None = None):
        self.dir = Path(cache_dir)
        self.events = events

    def _read(self, name: str) -> pd.DataFrame:
        p = self.dir / f"{name}.parquet"
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()

    # ---- 위치 매핑 ----
    @cached_property
    def stations(self) -> pd.DataFrame:
        st = self._read("bus_stations")
        if st.empty:
            return st
        st = st.rename(columns={"latitude": "lat", "longitude": "lon"})
        st["emd"] = st["stationAddress"].map(normalize_emd)
        known = st[st["emd"].notna()]
        rest = assign_emd(st[st["emd"].isna()].drop(columns=["emd"]), known[["lat", "lon", "emd"]].astype({"lat": float, "lon": float}))
        out = pd.concat([known.assign(method="address"), rest.assigned], ignore_index=True)
        out["lat"], out["lon"] = out["lat"].astype(float), out["lon"].astype(float)
        self._station_unmatched = len(rest.unmatched) + len(rest.out_of_range)
        return out

    @cached_property
    def ap_groups(self) -> pd.DataFrame:
        ap = self._read("wifi_ap_info")
        if ap.empty:
            return pd.DataFrame(columns=["apGroupName", "emd", "category"])
        ap = ap.rename(columns={"latitude": "lat", "longitude": "lon"})
        res = assign_emd(ap, self.stations[["lat", "lon", "emd"]], address_col="addressDong")
        self._ap_unmatched_groups = set(res.unmatched["apGroupName"]) | set(res.out_of_range["apGroupName"])
        g = res.assigned.groupby("apGroupName").agg(emd=("emd", lambda s: s.mode().iat[0]),
                                                    category=("category", lambda s: s.mode().iat[0]))
        return g.reset_index()

    @cached_property
    def station_of_emd(self) -> dict:
        ws = self._read("weather_stations")
        if ws.empty or self.stations.empty:
            return {}
        ws = ws.assign(lat=ws["latitude"].astype(float), lon=ws["longitude"].astype(float))
        cent = self.stations.groupby("emd")[["lat", "lon"]].mean()
        out = {}
        for emd, r in cent.iterrows():
            d = haversine_m(r["lat"], r["lon"], ws["lat"].to_numpy(), ws["lon"].to_numpy())
            out[emd] = ws["observatoryName"].iat[int(np.argmin(d))]
        return out

    @cached_property
    def weather(self) -> pd.DataFrame:
        w = self._read("weather_daily")
        if w.empty:
            return pd.DataFrame(columns=["date", "station", "rain_mm", "wind_max"])
        return pd.DataFrame({"date": pd.to_datetime(w["baseDate"].astype(str), format="%Y%m%d"),
                             "station": w["observatoryName"],
                             "rain_mm": pd.to_numeric(w["dailyRainfall"], errors="coerce"),
                             "wind_max": pd.to_numeric(w["maximumWindSpeed"], errors="coerce")})

    @cached_property
    def visitors(self) -> pd.Series:
        """월별 입도객 합계(방문목적별 입도객 현황 580의 목적 합). 인덱스 = 월 첫날."""
        v = self._read("visitors_purpose")
        if v.empty:
            return pd.Series(dtype=float)
        m = pd.to_datetime(v["dtYearMonth"].astype(str), format="%Y%m")
        return pd.to_numeric(v["visitorCnt"], errors="coerce").groupby(m).sum().sort_index()

    # ---- 신호 ----
    @cached_property
    def _frames(self) -> dict[str, pd.DataFrame]:
        pop = self._read("pop_domestic")
        if not pop.empty:
            pop = pop.assign(emd_full=(pop["city"] + " " + pop["emd"]).map(lambda x: normalize_emd(x)))
        wifi = self._read("wifi_ap_daily")
        if not wifi.empty:
            wifi = wifi.merge(self.ap_groups[["apGroupName", "emd"]], on="apGroupName", how="inner").rename(columns={"emd": "emd_full"})
        bus = self._read("bus_station_daily")
        if not bus.empty:
            bus = bus.merge(self.stations[["stationId", "emd"]], on="stationId", how="inner").rename(columns={"emd": "emd_full"})
        return {"유동인구": (pop, "visitPop"), "와이파이": (wifi, "userCount"), "버스": (bus, "userCount")}

    def signals(self) -> list[str]:
        return [k for k, (df, _) in self._frames.items() if not df.empty]

    def regions(self, signal: str) -> list[str]:
        df, _ = self._frames.get(signal, (pd.DataFrame(), None))
        return sorted(df["emd_full"].dropna().unique()) if not df.empty else []

    def island_series(self, signal: str) -> pd.Series:
        """읍면동에 매핑된 전체 합계(제주 전체). 매핑 실패분은 빠진다."""
        df, col = self._frames.get(signal, (pd.DataFrame(), None))
        if df.empty:
            return pd.Series(dtype=float)
        return to_daily(df[df["emd_full"].notna()], "baseDate", col)

    @cached_property
    def _daily(self) -> dict[str, pd.DataFrame]:
        """신호별 날짜 × 읍면동 일 합계 표(한 번만 계산). 수집되지 않은 날은 NaN."""
        out = {}
        for sig, (df, col) in self._frames.items():
            if df.empty:
                continue
            d = df[df["emd_full"].notna()]
            dates = pd.to_datetime(d["baseDate"].astype(str), format="%Y%m%d")
            vals = pd.to_numeric(d[col], errors="coerce")
            wide = vals.groupby([dates, d["emd_full"]]).sum(min_count=1).unstack()
            all_dates = pd.to_datetime(df["baseDate"].astype(str), format="%Y%m%d")
            out[sig] = wide.reindex(pd.date_range(all_dates.min(), all_dates.max(), freq="D"))
        return out

    def series(self, signal: str, emd: str) -> pd.Series:
        if signal not in self._daily:
            raise ToolError(f"no collected data for signal={signal!r}; available={self.signals()}")
        wide = self._daily[signal]
        if emd not in wide.columns:
            raise ToolError(f"no data for signal={signal!r} emd={emd!r}")
        return wide[emd].astype(float).rename(None).rename_axis(None)

    def quality(self) -> dict:
        as_of = {}
        for k, (df, _) in self._frames.items():
            if not df.empty:
                as_of[k] = str(pd.to_datetime(df["baseDate"].astype(str), format="%Y%m%d").max().date())
        _ = self.ap_groups
        return {"bus_stations": {"mapped": int(len(self.stations)), "unmatched": int(getattr(self, "_station_unmatched", 0))},
                "wifi_ap_groups": {"mapped": int(len(self.ap_groups)), "unmatched": len(getattr(self, "_ap_unmatched_groups", set()))},
                "as_of": as_of}
