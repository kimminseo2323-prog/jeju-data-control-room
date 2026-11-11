"""질문 분류(scan/explain/docs/other) 실험: 로컬 판단 모델(tev1) vs 키워드 규칙.

실행: python -m eval.intent_probe --model tev1:4b [--host http://127.0.0.1:11500]
결과: eval/results/intent_probe_<model>.json
질문 24개는 정답을 미리 정해 둔 한국어 질문이다(구어체·오타 없는 표현 위주, 실제 사용자 질문 아님).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.agent.local import route, rule_route

CASES = [
    ("7월에 유동인구가 이상하게 많았던 곳 알려줘", "scan"),
    ("5월에 이상 신호 있었던 읍면동 목록", "scan"),
    ("연동에서 6월에 이상한 날 있었어?", "scan"),
    ("버스 이용이 갑자기 줄어든 지역 찾아줘", "scan"),
    ("1월 와이파이 이용자가 튄 날짜가 언제야", "scan"),
    ("여름에 사람이 몰린 동네 어디야", "scan"),
    ("이호동 7월 28일에 사람이 왜 이렇게 많았어?", "explain"),
    ("성산읍 이상 신호 원인이 뭐야", "explain"),
    ("애월읍 와이파이 이용자가 12월 말에 급증한 이유", "explain"),
    ("어린이날에 왜 연동 유동인구가 늘었지", "explain"),
    ("한림읍 버스 승차가 2월에 줄어든 건 날씨 때문이야?", "explain"),
    ("구좌읍 방문객이 늘어난 배경을 설명해줘", "explain"),
    ("버스 데이터는 어디서 가져온 거야?", "docs"),
    ("유동인구 visitPop 컬럼은 무슨 뜻이야", "docs"),
    ("반출 가능한 데이터 기준이 뭐야?", "docs"),
    ("와이파이 AP 정보 API 일일 쿼터가 몇 건이야", "docs"),
    ("데이터명세서에 버스 카드 승하차 정보 항목 설명해줘", "docs"),
    ("결과물 권리는 누구한테 있어?", "docs"),
    ("오늘 점심 메뉴 추천해줘", "other"),
    ("이번 달 날씨 어때?", "other"),
    ("파이썬 리스트 정렬하는 법 알려줘", "other"),
    ("제주도 맛집 추천", "other"),
    ("너는 누구야?", "other"),
    ("서울 지하철 혼잡도 알려줘", "other"),
]

# 결합 방식(모델 + 규칙 보완)을 정하기 전에 따로 적어 둔 평가 전용 질문(설계에 쓰지 않음)
HELDOUT = [
    ("작년 추석 연휴에 평소보다 붐볐던 동네 보여줘", "scan"),
    ("3월 한 달 동안 와이파이 접속이 비정상적인 곳", "scan"),
    ("정류소 승차 인원이 크게 떨어진 날이 있었나", "scan"),
    ("중문동 관광객이 10월에 많아진 까닭은?", "explain"),
    ("표선면 유동인구 급감, 비 때문일까?", "explain"),
    ("서귀포 송산동 버스 승차가 늘어난 게 축제 영향인지 봐줘", "explain"),
    ("기상 데이터 관측소는 몇 군데야", "docs"),
    ("유동인구 데이터는 몇 시간 단위로 집계돼?", "docs"),
    ("센터 밖으로 가지고 나갈 수 있는 자료 범위", "docs"),
    ("주식 시세 알려줘", "other"),
    ("영어로 자기소개서 써줘", "other"),
    ("부산 해운대 인파 예측해줘", "other"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="tev1:4b")
    ap.add_argument("--host", default="http://127.0.0.1:11500")
    a = ap.parse_args()
    rows, ok_model, ok_rule = [], 0, 0
    for q, gold in CASES:
        t0 = time.perf_counter()
        pred, prob, backend = route(q, host=a.host, model=a.model)
        sec = time.perf_counter() - t0
        rule = rule_route(q)
        ok_model += pred == gold
        ok_rule += rule == gold
        rows.append({"question": q, "gold": gold, "model_pred": pred, "model_prob": round(prob, 3), "backend": backend,
                     "rule_pred": rule, "seconds": round(sec, 3)})
        print(f"{'O' if pred == gold else 'X'}{'o' if rule == gold else 'x'} gold={gold:8s} model={pred:8s} rule={rule:8s} {q}")
    n = len(CASES)
    summary = {"model": a.model, "n": n, "model_accuracy": ok_model / n, "rule_accuracy": ok_rule / n,
               "backend_used": sorted({r["backend"] for r in rows}),
               "sec_median": sorted(r["seconds"] for r in rows)[n // 2]}
    print(json.dumps(summary, ensure_ascii=False))
    out = Path("eval/results"); out.mkdir(parents=True, exist_ok=True)
    (out / f"intent_probe_{a.model.replace(':', '_')}.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
