import datetime as dt

import pandas as pd
import pytest

from app.ingest.hub_client import HubClient, QuotaExceeded
from app.ingest.jobs import Job
from app.ingest.run import export_completed
from tests.test_hub_client import FakeSession

JOB = Job("demo", 0, "API_DEMO", "데모", "daily")


def test_export_includes_only_fully_collected_requests(tmp_path):
    client = HubClient("K", session=FakeSession(tot=150), state_dir=tmp_path, max_calls_per_day=3, sleep=lambda s: None)
    client.fetch_all("API_DEMO", {"searchDate": "20250101"})          # 2페이지로 완료
    with pytest.raises(QuotaExceeded):
        client.fetch_all("API_DEMO", {"searchDate": "20250102"})      # 1페이지만 받고 중단
    out = tmp_path / "demo.parquet"
    info = export_completed(JOB, dt.date(2025, 1, 1), dt.date(2025, 1, 3), state_dir=tmp_path, out_path=out)
    df = pd.read_parquet(out)
    assert len(df) == 150 and set(df["_req_searchDate"]) == {"20250101"}
    assert info == {"requests": 3, "completed": 1, "rows": 150, "partial": True}
