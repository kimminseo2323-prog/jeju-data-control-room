"""허브 수집 작업 정의. API ID는 각 데이터 상세 페이지의 요청 URL에서 확인(2026-11-10).

mode
- daily  : searchDate=YYYYMMDD 하루 단위 요청
- range  : startDate/endDate(YYYYMMDD), 달 단위로 나눠 요청
- monthly: startDate/endDate(YYYYMM) 한 번에 요청
- once   : 파라미터 없이 1회
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Job:
    name: str
    hub_data_id: int          # jejudatahub.net/data/view/data/{id}
    api_id: str               # open.jejudatahub.net/api/proxy/{api_id}
    title: str
    mode: str
    extra: dict = field(default_factory=dict)
    date_param: str = "searchDate"   # daily 모드의 날짜 파라미터 이름
    daily_quota: int = 1000          # 허브 프로젝트 화면의 데이터별 일쿼터량(증설 승인 시 변경)


JOBS: dict[str, Job] = {j.name: j for j in [
    Job("pop_domestic", 583, "Daaa1t3at3tt8a8DD3t55538t35Dab1t", "읍면동 단위 내국인 유동인구", "range"),
    Job("pop_foreign_short", 589, "t18b1bttt8abaDt51b8aat85ttaa8t5b", "읍면동 단위 외국인 단기체류 유동인구", "range"),
    Job("wifi_ap_daily", 593, "1aa9D5DabtDt1at935b1tt5t1D95t5at", "와이파이 AP그룹별 일일 사용량", "daily"),
    Job("wifi_users_daily", 586, "tDtb1taa8aat816att6at6tba1aDtbba", "와이파이 일일 사용자수", "daily"),
    Job("wifi_ap_info", 618, "Dtb18ta1btbD1Da1a81aaDttab6tDabb", "제주 공공와이파이 AP 정보", "daily",
        date_param="baseDate"),
    Job("bus_station_daily", 613, "1b1ta1a1ba6t6a1ttt3bD6b1tb1t1D3t", "일일 정류소별 버스 이용자 정보", "range",
        {"moveType": "승차", "priceType": "일반", "payType": "카드"}, daily_quota=5000),   # 2026-11-11 증설 승인 확인
    Job("bus_total_daily", 617, "617bt7b7ttb1Datab7a7ttD6tbt7611t", "버스 일일 승객수 데이터", "range"),
    Job("bus_stations", 612, "DD11ab6a6t11D16baaa1a2tD26ata161", "버스 정류소 기본 정보", "once"),
    Job("bus_routes", 611, "aaatD6D1atta1611at1t6a1b6at1b11a", "버스 노선 기본 정보", "once"),
    Job("weather_daily", 579, "1aD5taat1attaa51Db1511b51ab9Da19", "일별 기상 정보", "daily"),
    Job("weather_stations", 578, "t1bab75a555a15715btaa7a5abaa1aab", "기상관측소 정보", "once"),
    Job("visitors_purpose", 580, "DtaDa0555D801Da508DbDtt5t1bat1ta", "방문목적별 입도객 현황", "monthly"),
    Job("visitors_country", 582, "tbata552bat15Daa585t52D5a5t818t2", "국가별 입도객 현황", "monthly"),
]}


def _days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def expand(job: Job, start: dt.date, end: dt.date) -> list[dict]:
    if job.mode == "once":
        return [dict(job.extra)]
    if job.mode == "daily":
        return [{job.date_param: d.strftime("%Y%m%d"), **job.extra} for d in _days(start, end)]
    if job.mode == "monthly":
        return [{"startDate": start.strftime("%Y%m"), "endDate": end.strftime("%Y%m"), **job.extra}]
    if job.mode == "range":
        out, cur = [], start
        while cur <= end:
            nxt = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
            last = min(end, nxt - dt.timedelta(days=1))
            out.append({"startDate": cur.strftime("%Y%m%d"), "endDate": last.strftime("%Y%m%d"), **job.extra})
            cur = last + dt.timedelta(days=1)
        return out
    raise ValueError(f"unknown mode {job.mode}")
