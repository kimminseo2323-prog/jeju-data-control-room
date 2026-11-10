"""허브 수집기 테스트 — 네트워크 없이 가짜 세션으로 동작 확인."""
import pytest

from app.ingest.hub_client import HubClient, QuotaExceeded, FetchFailed


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    """totCnt개 행을 limit 단위 페이지로 돌려주는 가짜 허브. fail_first 회는 500 오류."""

    def __init__(self, tot=250, fail_first=0):
        self.tot = tot
        self.fail_first = fail_first
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        if self.fail_first > 0:
            self.fail_first -= 1
            return FakeResponse(500)
        number, limit = int(params["number"]), int(params["limit"])
        start = (number - 1) * limit
        rows = [{"i": k} for k in range(start, min(start + limit, self.tot))]
        return FakeResponse(200, {"totCnt": self.tot, "hasMore": start + limit < self.tot, "data": rows})


def make_client(tmp_path, session, max_calls=1000):
    return HubClient("KEY", session=session, state_dir=tmp_path, max_calls_per_day=max_calls, sleep=lambda s: None)


def test_fetch_all_collects_every_page(tmp_path):
    s = FakeSession(tot=250)
    rows = make_client(tmp_path, s).fetch_all("API1", {"startDate": "20240101", "endDate": "20240101"})
    assert len(rows) == 250
    assert [c["number"] for c in s.calls] == [1, 2, 3]
    assert all(c["limit"] == 100 for c in s.calls)


def test_quota_stops_and_saves_checkpoint(tmp_path):
    s = FakeSession(tot=250)
    client = make_client(tmp_path, s, max_calls=2)
    with pytest.raises(QuotaExceeded) as e:
        client.fetch_all("API1", {"startDate": "20240101"})
    assert e.value.next_page == 3
    assert len(s.calls) == 2


def test_rerun_resumes_from_checkpoint(tmp_path):
    s = FakeSession(tot=250)
    with pytest.raises(QuotaExceeded):
        make_client(tmp_path, s, max_calls=2).fetch_all("API1", {"startDate": "20240101"})
    s2 = FakeSession(tot=250)
    rows = make_client(tmp_path, s2, max_calls=1000).fetch_all("API1", {"startDate": "20240101"})
    assert [c["number"] for c in s2.calls] == [3]
    assert len(rows) == 250  # 앞서 받은 200행 + 이번 50행


def test_quota_counter_persists_across_clients(tmp_path):
    with pytest.raises(QuotaExceeded):
        make_client(tmp_path, FakeSession(tot=250), max_calls=2).fetch_all("API1", {"a": "1"})
    with pytest.raises(QuotaExceeded):
        make_client(tmp_path, FakeSession(tot=250), max_calls=2).fetch_all("API1", {"a": "2"})


def test_http_error_retried_then_succeeds(tmp_path):
    s = FakeSession(tot=50, fail_first=2)
    rows = make_client(tmp_path, s).fetch_all("API1", {"x": "1"})
    assert len(rows) == 50


def test_http_error_three_times_fails(tmp_path):
    s = FakeSession(tot=50, fail_first=3)
    with pytest.raises(FetchFailed):
        make_client(tmp_path, s).fetch_all("API1", {"x": "1"})


def test_quota_counters_are_separate_files_per_api(tmp_path):
    c = make_client(tmp_path, FakeSession(tot=50))
    c.fetch_all("API_A", {"x": "1"})
    c.fetch_all("API_B", {"x": "1"})
    files = sorted(p.name for p in tmp_path.glob("quota_*"))
    assert len(files) == 2 and any("API_A" in f for f in files) and any("API_B" in f for f in files)


class QuotaSession(FakeSession):
    """처음 n번은 정상, 그다음은 허브처럼 403(쿼터 초과)."""

    def __init__(self, ok_calls, tot=250):
        super().__init__(tot=tot)
        self.ok_calls = ok_calls

    def get(self, url, params=None, timeout=None):
        if len(self.calls) >= self.ok_calls:
            self.calls.append(dict(params))
            return FakeResponse(403)
        return super().get(url, params, timeout)


def test_server_403_is_treated_as_quota_and_not_retried(tmp_path):
    s = QuotaSession(ok_calls=2)
    with pytest.raises(QuotaExceeded) as e:
        make_client(tmp_path, s).fetch_all("API1", {"d": "1"})
    assert e.value.next_page == 3 and len(s.calls) == 3  # 403은 재시도하지 않음
