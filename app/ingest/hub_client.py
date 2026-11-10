"""제주데이터허브 Open API 수집기.

- 페이징: number(1부터), limit(최대 100) → 응답 {totCnt, hasMore, data}
- 일일 쿼터: 데이터(API)별 호출 수를 state_dir에 날짜별로 기록, 한도 도달 시 QuotaExceeded
- 이어받기: (API, 파라미터)별로 받은 행을 jsonl에 쌓고 다음 페이지 번호를 저장
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import requests

BASE_URL = "https://open.jejudatahub.net/api/proxy"
PAGE_LIMIT = 100
MAX_ATTEMPTS = 3


class QuotaExceeded(Exception):
    def __init__(self, api_id: str, next_page: int):
        super().__init__(f"daily quota reached for {api_id}; resume at page {next_page}")
        self.api_id = api_id
        self.next_page = next_page


class FetchFailed(Exception):
    pass


class HubClient:
    def __init__(self, project_key: str, session=None, state_dir: Path | str = "data/state",
                 max_calls_per_day: int = 1000, sleep=time.sleep, today=None):
        self.project_key = project_key
        self.session = session or requests.Session()
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls_per_day
        self.sleep = sleep
        self.today = today or (lambda: dt.date.today().strftime("%Y%m%d"))

    # ---- quota ----
    def _quota_path(self, api_id: str) -> Path:
        # 데이터(API)별 파일 → 여러 수집기를 병렬로 돌려도 서로 덮어쓰지 않음
        return self.state_dir / f"quota_{self.today()}_{api_id}.txt"

    def calls_used(self, api_id: str) -> int:
        p = self._quota_path(api_id)
        return int(p.read_text("utf-8") or 0) if p.exists() else 0

    def _count_call(self, api_id: str) -> None:
        self._quota_path(api_id).write_text(str(self.calls_used(api_id) + 1), "utf-8")

    # ---- checkpoint ----
    def _job_paths(self, api_id: str, params: dict) -> tuple[Path, Path]:
        key = hashlib.sha1(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        return self.state_dir / f"{api_id}_{key}.json", self.state_dir / f"{api_id}_{key}.jsonl"

    # ---- fetching ----
    def _get_page(self, api_id: str, params: dict, number: int) -> dict:
        url = f"{BASE_URL}/{api_id}/{self.project_key}"
        query = {**params, "number": number, "limit": PAGE_LIMIT}
        last = None
        for attempt in range(MAX_ATTEMPTS):
            if self.calls_used(api_id) >= self.max_calls:
                raise QuotaExceeded(api_id, number)
            self._count_call(api_id)
            try:
                r = self.session.get(url, params=query, timeout=30)
                if r.status_code == 200:
                    return r.json()
                last = f"HTTP {r.status_code}"
            except requests.RequestException as e:  # 네트워크 오류도 재시도
                last = repr(e)
            self.sleep(2 ** attempt)
        raise FetchFailed(f"{api_id} page {number}: {last}")

    def fetch_all(self, api_id: str, params: dict) -> list[dict]:
        state_p, rows_p = self._job_paths(api_id, params)
        state = json.loads(state_p.read_text("utf-8")) if state_p.exists() else {"next_page": 1, "done": False}
        if not state["done"]:
            number = state["next_page"]
            while True:
                try:
                    page = self._get_page(api_id, params, number)
                except QuotaExceeded:
                    state_p.write_text(json.dumps({"next_page": number, "done": False}), "utf-8")
                    raise
                with rows_p.open("a", encoding="utf-8") as f:
                    for row in page.get("data", []):
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                number += 1
                if not page.get("hasMore"):
                    break
                state_p.write_text(json.dumps({"next_page": number, "done": False}), "utf-8")
            state_p.write_text(json.dumps({"next_page": number, "done": True}), "utf-8")
        if not rows_p.exists():
            return []
        return [json.loads(line) for line in rows_p.read_text("utf-8").splitlines() if line]
