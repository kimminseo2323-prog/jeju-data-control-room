"""실제 데이터 사례 질문을 Agent에 그대로 넣고 답변·판정·검증 결과를 기록한다(결과 설명서의 '실행 결과' 원본).

실행: python -m eval.real_cases --host http://127.0.0.1:11434
결과: eval/results/real_cases.json, eval/results/real_cases.md
정답(실제 원인)은 데이터로 확인되는 것만 적고, 확인되지 않으면 '미확인'으로 둔다.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

CASES = [
    ("성산읍 2024년 9월 16일에 유동인구가 왜 늘었어?", "추석 연휴(2024-09-16~18) — 공휴일 데이터로 확인"),
    ("이호동 2024년 7월 28일에 왜 사람이 많았어?", "미확인(여름 성수기 주말, 축제 데이터에 해당 행사 없음)"),
    ("이호동 2024년 8월 2일에 사람이 왜 많았어?", "이호테우축제 첫날 — 축제 데이터(761)로 확인"),
    ("삼도1동 2025년 3월 29일에 사람이 왜 많았어?", "미확인(축제 데이터에 맞는 행사 없음)"),
    ("2024년 9월에 유동인구가 이상하게 많았던 곳 알려줘", "-"),
    ("반출 가능한 데이터 기준이 뭐야?", "-"),
    ("오늘 점심 메뉴 추천해줘", "범위 밖 질문"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    a = ap.parse_args()
    os.environ["JUDGE_HOST"] = a.host
    from functools import partial

    import requests

    from app.agent.local import INTENT_KO, answer
    from app.agent.tools import Toolbox
    from app.config import ROOT
    from app.llm.judge import judge_cause
    from app.rag.corpus import load_corpus
    from app.rag.index import build_index
    from app.store.cache import CacheStore

    tb = Toolbox(CacheStore(ROOT / "data" / "cache"), build_index(load_corpus(ROOT)))
    rows, md = [], ["# 실제 데이터 사례 실행 기록", "", f"재현: `python -m eval.real_cases --host {a.host}` (로컬 판단 모델 tev1:4b)", ""]
    for q, truth in CASES:
        run = answer(q, tb, http=requests, judge=partial(judge_cause, host=a.host))
        judge = next((r.data for r in run.results.values() if r.tool == "judge_cause"), None)
        rows.append({"question": q, "known_cause": truth, "intent": run.intent, "router": run.router,
                     "slots": {"emd": run.slots.emd, "signal": run.slots.signal,
                               "date": str(run.slots.date.date()) if run.slots.date is not None else None},
                     "tools": [r.tool for r in run.results.values()], "verified": run.verified,
                     "verify_errors": run.verify_errors, "judgment": judge, "answer": run.final_text})
        md += [f"## {q}", "", f"- 분류: {INTENT_KO.get(run.intent, run.intent)} ({run.router}) · 검증: {'통과' if run.verified else '미통과'}"
               f" · 실행한 도구: {', '.join(rows[-1]['tools']) or '없음'}",
               f"- 데이터로 확인되는 실제 원인: {truth}"]
        if judge:
            md.append(f"- 판정: {judge['choice_ko']} {judge['probability']}% ({judge['backend']})")
        md += ["", "```text", run.final_text, "```", ""]
        print(f"{'OK ' if run.verified else 'NG '} {run.intent:8s} {judge['choice_ko'] + ' ' + str(judge['probability']) + '%' if judge else '':20s} {q}")
    out = Path("eval/results")
    (out / "real_cases.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), "utf-8")
    (out / "real_cases.md").write_text("\n".join(md), "utf-8")


if __name__ == "__main__":
    main()
