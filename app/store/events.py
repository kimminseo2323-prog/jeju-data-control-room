"""축제·행사(허브 761, VISIT JEJU 축제행사콘텐츠 CSV) → 읍면동 연결.

원본에는 장소 항목이 없다. 그래서 행사 이름에 읍면동 이름(또는 '이호'·'성산' 같은 지명)이
**명시된 경우에만** 연결하고, 추측으로 장소를 붙이지 않는다.
- 이름에 '취소'가 있으면 제외
- 기간이 7일을 넘는 행사(수주짜리 공원 축제 등)는 며칠짜리 급변의 원인으로 보기 어려워 제외(본 서비스 기준)
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.store.geo import EMD_43

EVENT_MAX_DAYS = 7
AMBIGUOUS = {"중앙", "천지", "연", "아라", "오라", "이도", "일도", "삼도"}   # 일반 단어와 겹치거나 동 이름이 여럿인 지명
COLUMNS = ["name", "start", "end", "emd"]


def _aliases() -> list[tuple[str, str]]:
    out = []
    for full in EMD_43:
        short = full.split(" ")[1]
        out.append((short, full))
        stem = re.sub(r"\d*[동읍면]$", "", short)
        if len(stem) >= 2 and stem not in AMBIGUOUS:
            out.append((stem, full))
    return sorted(out, key=lambda a: -len(a[0]))


def place_of(name: str) -> str | None:
    """지명이 단어 앞머리에 있을 때만 인정한다('월대천'의 '대천'처럼 다른 단어 중간이면 제외)."""
    hits = {full for alias, full in _aliases() if re.search(rf"(?<![가-힣]){re.escape(alias)}", name)}
    return hits.pop() if len(hits) == 1 else None


def load_events(csv_path: Path | str) -> pd.DataFrame:
    p = Path(csv_path)
    if not p.exists():
        return pd.DataFrame(columns=COLUMNS)
    d = pd.read_csv(p, encoding="cp949")
    ev = pd.DataFrame({"name": d["콘텐츠명"].astype(str).str.strip(),
                       "start": pd.to_datetime(d["시작일"], errors="coerce"),
                       "end": pd.to_datetime(d["종료일"], errors="coerce")}).dropna(subset=["start", "end"])
    ev = ev[~ev["name"].str.contains("취소")]
    ev = ev[(ev["end"] - ev["start"]).dt.days + 1 <= EVENT_MAX_DAYS]
    ev = ev.assign(emd=ev["name"].map(place_of)).dropna(subset=["emd"])
    return ev[COLUMNS].reset_index(drop=True)


def events_period(csv_path: Path | str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """행사 파일이 다루는 기간(올라온 행사의 첫 시작일 ~ 마지막 시작일). 이 기간 밖은 '행사 없음'이 아니라 '확인 불가'."""
    p = Path(csv_path)
    if not p.exists():
        return None
    s = pd.to_datetime(pd.read_csv(p, encoding="cp949")["시작일"], errors="coerce").dropna()
    return (s.min().normalize(), s.max().normalize()) if len(s) else None
