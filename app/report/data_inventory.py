"""수집 캐시 현황표(마크다운). 실행: python -m app.report.data_inventory → 데이터 활용 명세의 '수집 현황' 표에 붙인다."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
NAMES = {
    "pop_domestic": ("583", "읍면동 단위 내국인 유동인구"),
    "wifi_ap_daily": ("593", "와이파이 AP그룹별 일일 사용량"),
    "bus_station_daily": ("613", "일일 정류소별 버스 이용자 정보"),
    "weather_daily": ("579", "일별 기상 정보"),
    "weather_stations": ("578", "기상관측소 정보"),
    "visitors_purpose": ("580", "방문목적별 입도객 현황"),
    "visitors_country": ("582", "국가별 입도객 현황"),
    "bus_stations": ("612", "버스 정류소 기본 정보"),
    "bus_routes": ("611", "버스 노선 기본 정보"),
    "wifi_ap_info": ("618", "제주 공공와이파이 AP 정보"),
    "bus_total_daily": ("617", "버스 일일 승객수"),
    "wifi_users_daily": ("586", "와이파이 일일 사용자수"),
    "pop_foreign_short": ("589", "읍면동 단위 외국인 단기체류 유동인구"),
}


def inventory(cache: Path = ROOT / "data" / "cache") -> pd.DataFrame:
    rows = []
    for key, (hub_id, title) in NAMES.items():
        f = cache / f"{key}.parquet"
        if not f.exists():
            rows.append({"허브 ID": hub_id, "데이터": title, "파일": f"{key}.parquet", "행 수": 0, "기간": "미수집"})
            continue
        d = pd.read_parquet(f)
        col = next((c for c in ["baseDate", "dtYearMonth"] if c in d.columns), None)
        span = f"{d[col].astype(str).min()} ~ {d[col].astype(str).max()}" if col and key != "wifi_ap_info" else "기준일 1회"
        rows.append({"허브 ID": hub_id, "데이터": title, "파일": f"{key}.parquet", "행 수": f"{len(d):,}", "기간": span})
    return pd.DataFrame(rows)


def to_markdown(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


if __name__ == "__main__":
    print(to_markdown(inventory()))
