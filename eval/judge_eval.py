"""원인 판정 대규모 평가: 실제 데이터의 이상 구간 전체에 판정 모델을 돌려, 따로 확인되는 사실과 맞는지 본다.

실행: python -m eval.judge_eval --host http://127.0.0.1:11434 [--signals 유동인구,와이파이,버스]
결과: eval/results/judge_eval.json

정답(약한 정답, silver label) — 판정과 별개로 데이터에서 확인되는 사실:
- 공휴일: 가장 큰 날의 전날·당일·다음날이 공휴일(holidays 패키지) → holiday
- 축제·행사: 그 읍면동 이름이 행사명에 명시된 행사 기간(허브 761) → event
- 날씨: 일강수량 30mm 이상 또는 최대풍속 14m/s 이상(허브 579)이고 '감소' 이상 → weather
  (여러 개면 그중 하나를 고르면 정답)

측정
1. 일치율: 정답이 있는 이상 구간에서 판정이 정답 중 하나를 고른 비율.
2. 근거 제거 시험: 정답의 근거가 된 맥락을 지우고 다시 판정했을 때 그 원인을 '고르지 않는' 비율
   (근거 없이 원인을 지어내지 않는가).
3. 정답이 없는 구간의 판정 분포(판단 불가가 얼마나 나오는가).

한계: 정답이 판정에 넘기는 근거와 같은 자료에서 나오므로 '근거를 제대로 읽는가'를 재는 시험이며,
실제 원인을 현장에서 확인한 정답은 아니다. 공휴일 ±1일이 우연히 겹친 구간도 정답으로 들어간다.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path


def silver_labels(context: list[dict], direction: str) -> set[str]:
    kinds = {c["kind"] for c in context}
    out = set()
    if "holiday" in kinds:
        out.add("holiday")
    if "event" in kinds:
        out.add("event")
    if "weather" in kinds and direction == "down":
        out.add("weather")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--signals", default="유동인구,와이파이,버스")
    ap.add_argument("--threshold", type=float, default=3.5)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    os.environ["JUDGE_HOST"] = a.host
    from app.agent.tools import Toolbox
    from app.config import ROOT
    from app.llm.judge import judge_cause, rule_judge
    from app.store.cache import CacheStore

    store = CacheStore(ROOT / "data" / "cache")
    tb = Toolbox(store, index=None)
    cov = store.coverage
    rows = []
    t0 = time.perf_counter()
    for signal in a.signals.split(","):
        scan = tb.dispatch("scan_regions", {"signal": signal, "threshold": a.threshold, "top": 100000}, "R0").data
        for ep in scan["episodes"]:
            day = ep["peak_date"]
            co = tb.dispatch("find_co_movements", {"date": day, "emd": ep["emd"], "window": 1, "exclude_signal": signal}, "R2").data
            cx = tb.dispatch("check_context", {"date": day, "emd": ep["emd"], "signal": signal}, "R3").data
            evidence = {"anomaly": {"emd": ep["emd"], "signal": signal, "date": day, "pct": ep["peak_pct"], "kind": ep["kind"], "days": ep["days"]},
                        "context": cx["items"], "co_movements": co["co_movements"], "not_covered": cx["not_covered"]}
            labels = silver_labels(cx["items"], ep["direction"])
            j = judge_cause(evidence, host=a.host)
            r = rule_judge(evidence)
            row = {"signal": signal, "emd": ep["emd"], "date": day, "kind": ep["kind"], "direction": ep["direction"], "pct": ep["peak_pct"],
                   "in_coverage": not cx["not_covered"], "labels": sorted(labels), "choice": j.choice, "prob": round(j.probabilities.get(j.choice, 0), 3),
                   "backend": j.backend, "rule_choice": r.choice,
                   "context_kinds": sorted({c["kind"] for c in cx["items"]}), "co_signals": [c["signal"] for c in co["co_movements"]]}
            if labels:   # 근거 제거 시험: 정답 근거가 된 맥락만 지운다
                drop = {"holiday": "holiday", "event": "event", "weather": "weather"}
                ablated = dict(evidence, context=[c for c in cx["items"] if c["kind"] not in {drop[l] for l in labels}])
                ja = judge_cause(ablated, host=a.host)
                row["ablated_choice"] = ja.choice
            rows.append(row)
        print(f"{signal}: 이상 구간 {sum(1 for r in rows if r['signal'] == signal)}개")

    def rate(xs, f):
        xs = list(xs)
        return (round(sum(map(f, xs)) / len(xs), 3), len(xs)) if xs else (None, 0)

    labeled = [r for r in rows if r["labels"]]
    by_label = {}
    for lab in ("holiday", "event", "weather"):
        sub = [r for r in labeled if lab in r["labels"]]
        by_label[lab] = {"agree": rate(sub, lambda r: r["choice"] in r["labels"]),
                         "ablation_not_chosen": rate(sub, lambda r: r["ablated_choice"] not in r["labels"]),
                         "rule_agree": rate(sub, lambda r: r["rule_choice"] in r["labels"])}
    unlabeled = [r for r in rows if not r["labels"] and r["in_coverage"]]
    summary = {
        "host": a.host, "threshold": a.threshold, "episodes": len(rows), "backend": Counter(r["backend"] for r in rows),
        "labeled": len(labeled),
        "agree": rate(labeled, lambda r: r["choice"] in r["labels"]),
        "ablation_not_chosen": rate(labeled, lambda r: r["ablated_choice"] not in r["labels"]),
        "rule_agree": rate(labeled, lambda r: r["rule_choice"] in r["labels"]),
        "by_label": by_label,
        "unlabeled_in_coverage": len(unlabeled),
        "unlabeled_choices": Counter(r["choice"] for r in unlabeled),
        "outside_coverage": sum(not r["in_coverage"] for r in rows),
        "outside_coverage_choices": Counter(r["choice"] for r in rows if not r["in_coverage"]),
        "seconds": round(time.perf_counter() - t0, 1),
        "note": "정답은 판정 근거와 같은 자료에서 나온 약한 정답(근거를 제대로 읽는가를 재는 시험). 실제 원인을 현장에서 확인한 정답 아님.",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=dict))
    out = Path("eval/results"); out.mkdir(parents=True, exist_ok=True)
    name = "judge_eval" + (f"_{a.tag}" if a.tag else "")
    (out / f"{name}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1, default=dict), "utf-8")


if __name__ == "__main__":
    main()
