"""수집 캐시(data/cache/*.parquet) → 읍면동별 일 단위 신호, 기상, 행사, 데이터 품질 지표."""
from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from app.agent.tools import ToolError
from app.analytics.series import to_daily
from app.store.events import events_period, load_events
from app.store.geo import assign_emd, haversine_m, normalize_emd

SIGNALS = ["유동인구", "와이파이", "버스"]


def _norm_name(x) -> str:
    """정류소 이름 비교용: 한글·영문·숫자만 남긴다('제주도청(신제주로터리)' = '제주도청신제주로터리')."""
    return re.sub(r"[^가-힣A-Za-z0-9]", "", str(x))
EVENTS_CSV = "제주특별자치도주요행사정보.csv"   # 허브 761 파일 데이터, data/manual에 둔다


class CacheStore:
    def __init__(self, cache_dir: Path | str, events: pd.DataFrame | None = None):
        self.dir = Path(cache_dir)
        # 행사: 직접 주지 않으면 캐시 옆 data/manual의 761 CSV에서 '행사명에 지명이 명시된' 단기 행사만 읽는다
        self.events = events if events is not None else load_events(self.dir.parent / "manual" / EVENTS_CSV)
        self._events_period = None if events is not None else events_period(self.dir.parent / "manual" / EVENTS_CSV)

    @cached_property
    def coverage(self) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
        """맥락 근거 자료별 제공 기간. 이 기간 밖의 날짜는 '없음'이 아니라 '확인 불가'로 다룬다."""
        out = {}
        w = self.weather
        if len(w):
            out["weather"] = (w["date"].min(), w["date"].max())
        if self._events_period:
            out["event"] = self._events_period
        v = self.visitors.dropna()
        if len(v):
            out["visitors"] = (v.index.min(), v.index.max() + pd.offsets.MonthEnd(0))
        return out

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
        self._ap_points = res.assigned.assign(lat=res.assigned["lat"].astype(float), lon=res.assigned["lon"].astype(float))[["lat", "lon", "emd"]]
        g = res.assigned.groupby("apGroupName").agg(emd=("emd", lambda s: s.mode().iat[0]),
                                                    category=("category", lambda s: s.mode().iat[0]))
        return g.reset_index()

    @cached_property
    def centroids(self) -> pd.DataFrame:
        """읍면동 대표 좌표 = 정류소 좌표 평균. 정류소가 없는 읍면동(우도면 등)은 와이파이 AP 좌표 평균으로 대신한다."""
        if self.stations.empty:
            return pd.DataFrame(columns=["lat", "lon"])
        cent = self.stations.groupby("emd")[["lat", "lon"]].mean()
        self.ap_groups
        ap = getattr(self, "_ap_points", pd.DataFrame(columns=["lat", "lon", "emd"]))
        extra = ap[~ap["emd"].isin(cent.index)].groupby("emd")[["lat", "lon"]].mean()
        return pd.concat([cent, extra])

    NEIGHBOR_K, NEIGHBOR_KM = 3, 15.0   # 가까운 3곳, 대표 좌표 사이 15km 이내(본 서비스 임의 기준, 읍면 지역이 넓어서)

    def neighbors(self, emd: str) -> list[str]:
        """대표 좌표가 가까운 읍면동(최대 NEIGHBOR_K곳, NEIGHBOR_KM 이내). 섬(우도·추자)처럼 멀면 빈 목록."""
        cent = self.centroids
        if emd not in cent.index:
            return []
        r = cent.loc[emd]
        d = pd.Series(haversine_m(r["lat"], r["lon"], cent["lat"].to_numpy(float), cent["lon"].to_numpy(float)), index=cent.index).drop(emd)
        return list(d[d <= self.NEIGHBOR_KM * 1000].nsmallest(self.NEIGHBOR_K).index)

    @cached_property
    def station_of_emd(self) -> dict:
        ws = self._read("weather_stations")
        if ws.empty or self.stations.empty:
            return {}
        ws = ws.assign(lat=ws["latitude"].astype(float), lon=ws["longitude"].astype(float))
        cent = self.centroids
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
            bus = self._map_bus(bus)
        return {"유동인구": (pop, "visitPop"), "와이파이": (wifi, "userCount"), "버스": (bus, "userCount")}

    def _map_bus(self, bus: pd.DataFrame) -> pd.DataFrame:
        """버스 이용(613) → 읍면동. 613과 정류소 정보(612)의 정류소ID 체계가 달라(7자리 vs 9자리) ID가 겹치지 않는다.
        ① ID가 같으면 ID로 ② 아니면 정규화한 정류소 이름이 '한 읍면동에만' 있을 때 이름으로 연결
        ③ 같은 이름이 여러 읍면동에 있으면(경계의 큰 정류소 등) 추측하지 않고 '모호'로, 나머지는 '매칭 실패'로 집계."""
        st = self.stations
        by_id = dict(zip(st["stationId"].astype(str), st["emd"]))
        names = st.assign(n=st["stationName"].map(_norm_name)).groupby("n")["emd"].agg(lambda s: set(s.dropna()))
        unique = {k: next(iter(v)) for k, v in names.items() if len(v) == 1}
        ambiguous = {k for k, v in names.items() if len(v) > 1}
        n = bus["stationName"].map(_norm_name) if "stationName" in bus else pd.Series("", index=bus.index)
        e_id = bus["stationId"].astype(str).map(by_id)
        e_name = n.map(unique)
        users = pd.to_numeric(bus["userCount"], errors="coerce").fillna(0)
        total = users.sum() or 1
        share = lambda m: round(float(users[m].sum() / total * 100), 1)
        self._bus_mapping = {"by_id": share(e_id.notna()), "by_name": share(e_id.isna() & e_name.notna()),
                             "ambiguous_name": share(e_id.isna() & e_name.isna() & n.isin(ambiguous)),
                             "unmatched": share(e_id.isna() & e_name.isna() & ~n.isin(ambiguous))}
        return bus.assign(emd_full=e_id.fillna(e_name)).dropna(subset=["emd_full"])

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
                "bus_usage": getattr(self, "_bus_mapping", {}),
                "wifi_ap_groups": {"mapped": int(len(self.ap_groups)), "unmatched": len(getattr(self, "_ap_unmatched_groups", set()))},
                "as_of": as_of}
