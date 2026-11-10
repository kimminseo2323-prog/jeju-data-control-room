"""전체 수집 계획. 실행: python -m app.ingest.plan

API별 일일 쿼터(1,000회)가 따로 있으므로 작업마다 별도 프로세스로 병렬 실행한다.
쿼터에 걸린 작업은 멈춘 곳을 저장하고 끝나며, 다음 날 같은 명령으로 이어받는다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data" / "state" / "logs"

# (작업, 시작, 끝) — 주 분석 기간 2024-04-01~2025-03-31, 저비용 신호는 최근까지
PLAN = [
    ("bus_stations", "2025-03-31", "2025-03-31"),
    ("bus_routes", "2025-03-31", "2025-03-31"),
    ("weather_stations", "2025-03-31", "2025-03-31"),
    ("visitors_purpose", "2024-04-01", "2025-07-31"),
    ("visitors_country", "2024-04-01", "2025-07-31"),
    ("bus_total_daily", "2024-04-01", "2026-11-05"),
    ("wifi_users_daily", "2024-04-01", "2026-11-05"),
    ("weather_daily", "2024-04-01", "2025-04-30"),
    ("pop_domestic", "2024-04-01", "2025-03-31"),
    ("wifi_ap_daily", "2024-10-01", "2025-03-31"),
    ("bus_station_daily", "2025-01-01", "2025-03-31"),
]


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    procs = []
    # 와이파이 AP 정보(618)는 페이지 순서가 호출마다 바뀌어 반복 수집 후 합친다(app/ingest/union.py)
    if not (ROOT / "data" / "cache" / "wifi_ap_info.parquet").exists():
        subprocess.run([sys.executable, "-m", "app.ingest.union", "20250331"], cwd=ROOT, check=False)
    for job, start, end in PLAN:
        log = open(LOG / f"{job}.log", "a", encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-m", "app.ingest.run", job, start, end], cwd=ROOT,
                             stdout=log, stderr=subprocess.STDOUT, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        procs.append((job, p, log))
    for job, p, log in procs:
        code = p.wait()
        log.close()
        status = {0: "완료", 2: "쿼터 소진·실패(로그 확인, 내일 이어받기)"}.get(code, f"오류 코드 {code}")
        print(f"{job:20s} {status}")


if __name__ == "__main__":
    main()
