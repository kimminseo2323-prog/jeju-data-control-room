import datetime as dt

from app.ingest.jobs import JOBS, expand


def test_daily_job_expands_one_request_per_day():
    job = JOBS["wifi_ap_daily"]
    reqs = expand(job, dt.date(2024, 10, 1), dt.date(2024, 10, 3))
    assert reqs == [{"searchDate": "20241001"}, {"searchDate": "20241002"}, {"searchDate": "20241003"}]


def test_range_job_splits_by_month_and_keeps_filters():
    job = JOBS["bus_station_daily"]
    reqs = expand(job, dt.date(2025, 1, 30), dt.date(2025, 2, 2))
    assert reqs == [
        {"startDate": "20250130", "endDate": "20250131", "moveType": "승차", "priceType": "일반", "payType": "카드"},
        {"startDate": "20250201", "endDate": "20250202", "moveType": "승차", "priceType": "일반", "payType": "카드"},
    ]


def test_monthly_job_uses_yyyymm():
    reqs = expand(JOBS["visitors_purpose"], dt.date(2024, 4, 1), dt.date(2025, 3, 31))
    assert reqs == [{"startDate": "202404", "endDate": "202503"}]


def test_once_job_has_single_request():
    assert expand(JOBS["bus_stations"], dt.date(2024, 4, 1), dt.date(2025, 3, 31)) == [{}]


def test_ap_info_uses_basedate_param():
    assert expand(JOBS["wifi_ap_info"], dt.date(2025, 3, 31), dt.date(2025, 3, 31)) == [{"baseDate": "20250331"}]


def test_daily_quota_per_job_reflects_approved_increase():
    from app.ingest.jobs import JOBS
    assert JOBS["bus_station_daily"].daily_quota == 5000      # 2026-11-11 허브 프로젝트 화면에서 '승인' 확인
    assert JOBS["pop_domestic"].daily_quota == 1000
