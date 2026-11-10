"""tev1 로컬 판단 모델 사전 실험: 원인 판정 10건(정답을 정해 둔 한국어 사례)과 응답 시간.

실행: python -m eval.tev1_probe --model tev1:0.8b --host http://127.0.0.1:11500 [--cpu]
결과: eval/results/tev1_probe_<model>.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

CAUSES = {
    "weather": "날씨(강한 비·바람·태풍 등)가 주된 원인이다.",
    "holiday": "공휴일·연휴가 주된 원인이다.",
    "event": "축제·행사가 주된 원인이다.",
    "tourism_demand": "관광 수요가 늘거나 줄어 같은 지역의 여러 신호가 함께 움직였다.",
    "data_issue": "실제 변화가 아니라 데이터 누락·집계 오류로 보인다.",
    "unknown": "주어진 근거로는 원인을 판단하기 어렵다.",
}

CASES = [
    ("성산읍 방문인구 41% 증가. 같은 날 버스 승차 +35%, 성산일출봉 와이파이 이용자 +52%. 공휴일 아님, 강수 0mm, 등록된 행사 없음.", "tourism_demand"),
    ("애월읍 방문인구 38% 감소. 같은 날 애월 관측소 일강수량 112mm, 최대풍속 21m/s. 버스 승차 -30%.", "weather"),
    ("구좌읍 방문인구 47% 증가. 이날은 설날 연휴 이틀째. 강수 없음. 행사 없음.", "holiday"),
    ("표선면 방문인구 60% 증가. 같은 날 '표선해변 하얀모래 축제' 진행 중(표선면). 날씨 맑음, 공휴일 아님.", "event"),
    ("연동 방문인구가 0으로 기록됨. 같은 날 버스 승차와 와이파이 이용은 평소 수준. 이 날짜만 데이터 행 수가 평소의 3%.", "data_issue"),
    ("중문동 와이파이 이용자 25% 감소. 다른 신호는 평소 수준. 날씨·공휴일·행사 정보 없음.", "unknown"),
    ("한림읍 버스 승차 44% 감소. 한림 관측소 최대풍속 26m/s, 태풍 영향권. 방문인구도 -29%.", "weather"),
    ("우도면 방문인구 55% 증가, 와이파이 +61%. 추석 연휴 첫날. 강수 0mm.", "holiday"),
    ("건입동 방문인구 33% 증가. '탐라문화제' 개최(건입동 일대). 같은 날 버스 승차 +21%. 공휴일 아님.", "event"),
    ("노형동 버스 승차가 평소의 4배로 기록됨. 해당 날짜 정류소 1곳의 값만 비정상적으로 큼, 다른 정류소와 방문인구는 평소 수준.", "data_issue"),
]


def ask(host: str, model: str, state: str, cpu: bool) -> tuple[dict, float]:
    body = {"model": model, "state": state, "questions": {
        "cause": {"type": "choice", "instructions": "Which listed cause best explains this anomaly in Jeju tourism/transport data? Judge only from the given evidence.",
                  "criteria": CAUSES}}}
    if cpu:
        body["options"] = {"num_gpu": 0}
    t0 = time.perf_counter()
    r = requests.post(f"{host}/v1/systemone", json=body, timeout=300)
    dt_s = time.perf_counter() - t0
    r.raise_for_status()
    return r.json(), dt_s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="tev1:0.8b")
    ap.add_argument("--host", default="http://127.0.0.1:11500")
    ap.add_argument("--cpu", action="store_true", help="GPU 끄고 CPU만 사용(센터 PC 가정)")
    a = ap.parse_args()
    rows, correct = [], 0
    for state, gold in CASES:
        res, sec = ask(a.host, a.model, state, a.cpu)
        ans = res.get("answers", res).get("cause", {}) if isinstance(res, dict) else {}
        pred = ans.get("choice")
        correct += pred == gold
        rows.append({"state": state, "gold": gold, "pred": pred, "confidence": ans.get("confidence"),
                     "probabilities": ans.get("probabilities"), "seconds": round(sec, 2)})
        print(f"{'O' if pred == gold else 'X'} gold={gold:15s} pred={pred} conf={ans.get('confidence')} {sec:.1f}s")
    secs = [r["seconds"] for r in rows]
    summary = {"model": a.model, "cpu_only": a.cpu, "accuracy": correct / len(CASES), "n": len(CASES),
               "sec_first": secs[0], "sec_median_rest": sorted(secs[1:])[len(secs[1:]) // 2]}
    print(json.dumps(summary, ensure_ascii=False))
    out = Path("eval/results"); out.mkdir(parents=True, exist_ok=True)
    tag = a.model.replace(":", "_") + ("_cpu" if a.cpu else "_gpu")
    (out / f"tev1_probe_{tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
