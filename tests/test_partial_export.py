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


def test_run_exports_completed_requests_when_server_fails(tmp_path, monkeypatch):
    """서버 오류(HTTP 500 등)로 멈춰도, 쿼터 소진 때처럼 끝까지 받은 달은 캐시로 내보낸다."""
    import app.ingest.run as run_mod
    from app.ingest.hub_client import FetchFailed

    class FailingClient:
        def __init__(self, *a, **k):
            self.n = 0

        def fetch_all(self, api_id, params):
            self.n += 1
            if self.n == 2:
                raise FetchFailed("API_DEMO page 1: HTTP 500")
            return [{"v": 1}]

        def calls_used(self, api_id):
            return self.n

    calls = []
    monkeypatch.setenv("JEJU_HUB_PROJECT_KEY", "K")
    monkeypatch.setattr(run_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(run_mod, "HubClient", FailingClient)
    monkeypatch.setitem(run_mod.JOBS, "demo", JOB)
    monkeypatch.setattr(run_mod, "export_completed", lambda job, s, e: calls.append((job.name, s, e)) or {"completed": 1})
    assert run_mod.run("demo", dt.date(2025, 1, 1), dt.date(2025, 1, 3)) is False
    assert calls == [("demo", dt.date(2025, 1, 1), dt.date(2025, 1, 3))]
