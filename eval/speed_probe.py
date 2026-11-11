"""질문 1건 처리 시간(질문 → 검증된 답변) 측정: 실제 데이터 캐시 + 로컬 판단 모델(tev1) 서버.

실행: python -m eval.speed_probe --host http://127.0.0.1:11434 --tag gpu
     (CPU만 쓰는 서버, 코어 수를 줄인 서버 등 host만 바꿔 여러 번 실행)
결과: eval/results/speed_probe_<tag>.json

- 모델 서버에 가는 요청(질문 분류·원인 판정)은 따로 시간을 잰다.
- 첫 질문은 모델을 메모리에 올리는 시간이 포함되므로 '첫 질문'으로 따로 적는다.
- 측정 PC와 센터 PC 사양이 다르므로 이 값은 센터 실측값이 아니다.
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import requests

QUESTIONS = [
    ("explain", "이호동 7월 28일에 왜 사람이 많았어?"),
    ("explain", "성산읍 추석 연휴에 유동인구가 왜 늘었어?"),
    ("explain", "삼도1동 2025년 3월 29일에 사람이 왜 많았어?"),
    ("scan", "7월에 유동인구가 이상하게 많았던 곳 알려줘"),
    ("docs", "버스 데이터는 어디서 가져온 거야?"),
    ("other", "오늘 점심 메뉴 추천해줘"),
]


class TimedHttp:
    """requests 대신 넘겨 모델 서버 요청 시간만 모은다(주소·본문은 그대로)."""

    def __init__(self):
        self.calls: list[tuple[str, float]] = []

    def post(self, url, **kw):
        t0 = time.perf_counter()
        try:
            return requests.post(url, **kw)
        finally:
            kind = next(iter(kw.get("json", {}).get("questions", {"?": 0})))
            self.calls.append((kind, time.perf_counter() - t0))

    def get(self, url, **kw):
        return requests.get(url, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="Ollama 주소(예: http://127.0.0.1:11434)")
    ap.add_argument("--tag", required=True, help="결과 파일 이름표(예: gpu, cpu12, cpu6)")
    ap.add_argument("--note", default="", help="측정 조건 메모")
    ap.add_argument("--repeat", type=int, default=2, help="질문 묶음 반복 횟수(첫 바퀴 첫 질문은 모델 적재 포함)")
    ap.add_argument("--pin", default="", help="이 파이썬 프로세스를 고정할 논리 CPU 마스크(예: 0x555 = 0,2,4,6,8,10). Windows 전용")
    a = ap.parse_args()
    if a.pin:   # 도구 실행(탐지·훑기) 시간도 코어 수를 줄인 조건에서 재기 위해
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
        if not k32.SetProcessAffinityMask(k32.GetCurrentProcess(), ctypes.c_size_t(int(a.pin, 16))):
            raise SystemExit("CPU 고정 실패")

    import os
    os.environ["JUDGE_HOST"] = a.host          # app 모듈을 불러오기 전에 지정해야 기본 주소로 쓰인다
    from functools import partial

    from app.agent.local import answer
    from app.agent.tools import Toolbox
    from app.config import ROOT
    from app.llm.judge import judge_cause
    from app.rag.corpus import load_corpus
    from app.rag.index import build_index
    from app.store.cache import CacheStore

    t0 = time.perf_counter()
    tb = Toolbox(CacheStore(ROOT / "data" / "cache"), build_index(load_corpus(ROOT)))
    setup_s = time.perf_counter() - t0

    rows = []
    for rnd in range(a.repeat):
        for kind, q in QUESTIONS:
            http = TimedHttp()
            t1 = time.perf_counter()
            run = answer(q, tb, http=http, judge=partial(judge_cause, http=http, host=a.host))
            total = time.perf_counter() - t1
            model_s = sum(s for _, s in http.calls)
            rows.append({"round": rnd + 1, "kind": kind, "question": q, "intent": run.intent, "router": run.router,
                         "verified": run.verified, "total_s": round(total, 2), "model_s": round(model_s, 2),
                         "other_s": round(total - model_s, 2),
                         "model_calls": [{"what": k, "s": round(s, 2)} for k, s in http.calls]})
            print(f"[{rnd + 1}] {kind:7s} total={total:5.2f}s model={model_s:5.2f}s router={run.router} verified={run.verified}  {q}")

    warm = rows[1:]   # 첫 질문(모델 적재 포함) 제외
    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else None
    by_kind = {k: med([r["total_s"] for r in warm if r["kind"] == k]) for k, _ in QUESTIONS}
    summary = {"tag": a.tag, "host": a.host, "note": a.note, "pin": a.pin or None, "machine": platform.processor(), "setup_s": round(setup_s, 2),
               "first_question_s": rows[0]["total_s"], "median_total_s_by_kind": by_kind,
               "max_total_s_warm": max(r["total_s"] for r in warm),
               "all_model_backed": all(r["router"] != "rule" for r in rows)}
    print(json.dumps(summary, ensure_ascii=False))
    out = Path("eval/results"); out.mkdir(parents=True, exist_ok=True)
    (out / f"speed_probe_{a.tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
