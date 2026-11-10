"""수집 실행: python -m app.ingest.run <job> <start YYYY-MM-DD> <end YYYY-MM-DD>

쿼터에 걸리면 진행 상황을 저장하고 종료 → 다음 날 같은 명령으로 이어받기.
모든 요청이 끝나면 data/cache/<job>.parquet 로 합쳐 저장.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from app.ingest.hub_client import FetchFailed, HubClient, QuotaExceeded
from app.ingest.jobs import JOBS, expand

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "state"
CACHE = ROOT / "data" / "cache"


def run(job_name: str, start: dt.date, end: dt.date) -> bool:
    load_dotenv(ROOT / ".env")
    key = os.getenv("JEJU_HUB_PROJECT_KEY", "").strip()
    if not key or key.startswith("여기에"):
        sys.exit("JEJU_HUB_PROJECT_KEY가 .env에 없습니다 (.env.example 참고)")
    job = JOBS[job_name]
    client = HubClient(key, state_dir=STATE)
    reqs = expand(job, start, end)
    frames = []
    for i, params in enumerate(reqs, 1):
        try:
            rows = client.fetch_all(job.api_id, params)
        except QuotaExceeded as e:
            print(f"[{job_name}] 쿼터 소진: {i}/{len(reqs)}번째 요청 {params} 의 {e.next_page}페이지부터 내일 이어받기")
            return False
        except FetchFailed as e:
            print(f"[{job_name}] 실패: {e}")
            return False
        df = pd.DataFrame(rows)
        for k, v in params.items():
            df[f"_req_{k}"] = v
        frames.append(df)
        print(f"[{job_name}] {i}/{len(reqs)} {params} rows={len(df)} calls_today={client.calls_used(job.api_id)}")
    CACHE.mkdir(parents=True, exist_ok=True)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out = out.drop_duplicates()
    out.to_parquet(CACHE / f"{job_name}.parquet", index=False)
    print(f"[{job_name}] 완료 rows={len(out)} → {CACHE / (job_name + '.parquet')}")
    return True


if __name__ == "__main__":
    name, s, e = sys.argv[1], sys.argv[2], sys.argv[3]
    ok = run(name, dt.date.fromisoformat(s), dt.date.fromisoformat(e))
    sys.exit(0 if ok else 2)
