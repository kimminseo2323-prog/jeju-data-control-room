"""읍면동(행정동 43개) 기준 위치 매핑.

기준 목록: 제주빅데이터센터 데이터명세서 v13, 4-11 내국인 유동인구(읍면동)_v02 [참고1].
매핑 순서: ① 주소 문자열에서 행정동 이름 찾기 → ② 안 되면 기준점(예: 정류소)의 최근접 행정동
(max_dist_m 이내) → ③ 둘 다 실패하면 unmatched로 따로 반환(조용히 버리지 않음).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

EMD_43 = [
    "제주시 한림읍", "제주시 애월읍", "제주시 구좌읍", "제주시 조천읍", "제주시 한경면", "제주시 추자면", "제주시 우도면",
    "제주시 일도1동", "제주시 일도2동", "제주시 이도1동", "제주시 이도2동", "제주시 삼도1동", "제주시 삼도2동",
    "제주시 용담1동", "제주시 용담2동", "제주시 건입동", "제주시 화북동", "제주시 삼양동", "제주시 봉개동",
    "제주시 아라동", "제주시 오라동", "제주시 연동", "제주시 노형동", "제주시 외도동", "제주시 이호동", "제주시 도두동",
    "서귀포시 대정읍", "서귀포시 남원읍", "서귀포시 성산읍", "서귀포시 안덕면", "서귀포시 표선면",
    "서귀포시 송산동", "서귀포시 정방동", "서귀포시 중앙동", "서귀포시 천지동", "서귀포시 효돈동", "서귀포시 영천동",
    "서귀포시 동홍동", "서귀포시 서홍동", "서귀포시 대륜동", "서귀포시 대천동", "서귀포시 중문동", "서귀포시 예래동",
]
JEJU_LAT = (33.1, 34.0)   # 추자도(약 33.96) 포함 — 이전 33.6 상한은 추자면 AP를 범위 밖으로 버렸음
JEJU_LON = (126.1, 127.0)


def _city_of(text: str) -> str | None:
    for c in ("서귀포시", "제주시"):  # '서귀포시'를 먼저 봐야 '제주시'와 혼동 없음
        if c in text:
            return c
    return None


def normalize_emd(text: str, city: str | None = None) -> str | None:
    if not isinstance(text, str):
        return None
    city = city or _city_of(text)
    tokens = re.split(r"\s+", text.strip())
    for full in EMD_43:
        c, emd = full.split(" ")
        if city and c != city:
            continue
        if emd in tokens:
            return full
    # 읍·면 이름 줄임 표기(예: '성산' → '성산읍')는 시가 주어졌을 때만 허용
    if city:
        for full in EMD_43:
            c, emd = full.split(" ")
            if c == city and emd[-1] in "읍면" and emd[:-1] in tokens:
                return full
    return None


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


@dataclass
class AssignResult:
    assigned: pd.DataFrame
    unmatched: pd.DataFrame
    out_of_range: pd.DataFrame


def assign_emd(points: pd.DataFrame, reference: pd.DataFrame, address_col: str | None = None,
               max_dist_m: float = 2000) -> AssignResult:
    """points: lat, lon(+주소) / reference: lat, lon, emd(주소로 확정된 기준점)."""
    pts = points.copy()
    pts["lat"] = pd.to_numeric(pts["lat"], errors="coerce")
    pts["lon"] = pd.to_numeric(pts["lon"], errors="coerce")
    in_range = pts["lat"].between(*JEJU_LAT) & pts["lon"].between(*JEJU_LON)
    out_of_range, pts = pts[~in_range].copy(), pts[in_range].copy()

    emd, method = [], []
    ref_lat, ref_lon, ref_emd = reference["lat"].to_numpy(float), reference["lon"].to_numpy(float), reference["emd"].to_numpy()
    for _, row in pts.iterrows():
        e = normalize_emd(row[address_col]) if address_col else None
        if e:
            emd.append(e); method.append("address"); continue
        if len(ref_lat):
            d = haversine_m(row["lat"], row["lon"], ref_lat, ref_lon)
            k = int(np.argmin(d))
            if d[k] <= max_dist_m:
                emd.append(ref_emd[k]); method.append("nearest"); continue
        emd.append(None); method.append(None)
    pts["emd"], pts["method"] = emd, method
    return AssignResult(assigned=pts[pts["emd"].notna()].reset_index(drop=True),
                        unmatched=pts[pts["emd"].isna()].drop(columns=["emd", "method"]).reset_index(drop=True),
                        out_of_range=out_of_range.reset_index(drop=True))
