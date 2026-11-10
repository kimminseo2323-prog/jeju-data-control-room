"""페이지 순서가 호출마다 바뀌는 API(예: 618 와이파이 AP 정보) 대응.

같은 요청을 여러 번 받아 고유 키 기준으로 합치고, 연속 stable_rounds회 새 행이 없으면 멈춘다.
실행(AP 정보): python -m app.ingest.union 20250331
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable


def union_until_stable(fetch: Callable[[], list[dict]], key: Callable[[dict], object],
                       max_rounds: int = 10, stable_rounds: int = 2) -> tuple[list[dict], int]:
    seen: dict = {}
    quiet = 0
    for rnd in range(1, max_rounds + 1):
        before = len(seen)
        for row in fetch():
            seen.setdefault(key(row), row)
        quiet = quiet + 1 if len(seen) == before else 0
        if quiet >= stable_rounds:
            return list(seen.values()), rnd
    return list(seen.values()), max_rounds


def main(base_date: str) -> None:
    import os

    import pandas as pd
    import requests
    from dotenv import load_dotenv

    from app.ingest.hub_client import HubClient
    from app.ingest.jobs import JOBS

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    job = JOBS["wifi_ap_info"]
    client = HubClient(os.environ["JEJU_HUB_PROJECT_KEY"], state_dir=root / "data" / "state")

    def fetch() -> list[dict]:
        rows, n = [], 1
        while True:
            page = client._get_page(job.api_id, {"baseDate": base_date}, n)
            rows += page.get("data", [])
            if not page.get("hasMore"):
                return rows
            n += 1

    rows, rounds = union_until_stable(fetch, key=lambda r: r.get("macAddress"), max_rounds=12, stable_rounds=2)
    out = root / "data" / "cache" / "wifi_ap_info.parquet"
    pd.DataFrame(rows).to_parquet(out, index=False)
    print(f"[wifi_ap_info] {rounds}회 반복 수집, 고유 AP {len(rows)}개 → {out} (API 호출 누계 {client.calls_used(job.api_id)})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "20250331")
