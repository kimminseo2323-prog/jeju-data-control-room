"""문서 검색(질문하기 '문서 검색') 평가: 질문마다 답이 있는 문서를 미리 정해 두고, 상위 3개 안에 들어오는지 본다.

실행: python -m eval.rag_probe [--tag before]
결과: eval/results/rag_probe_<tag>.json

- design 10개: 2026-11-11 실제 사례 점검에서 '반출 기준' 질문이 재무 명세서를 돌려준 것을 보고 만든 질문.
  검색 개선(제목 가중·문서 추가)을 고를 때 이 묶음만 봤다.
- heldout 6개: 개선 전에 함께 적어 두고, 개선을 정한 뒤 한 번만 확인한 질문.
- 정답 문서는 doc_id 앞부분으로 지정(여러 개면 그중 하나면 정답). 질문은 직접 만든 것이며 실제 사용자 질문이 아니다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DESIGN = [
    ("반출 가능한 데이터 기준이 뭐야?", ["src:notice48", "board:3."]),
    ("결과물 권리는 누구한테 있어?", ["board:5."]),
    ("버스 데이터는 어디서 가져온 거야?", ["md:데이터_활용_명세", "src:613"]),
    ("와이파이 AP 정보 API 일일 쿼터가 몇 건이야", ["md:데이터_활용_명세", "src:618"]),
    ("유동인구 visitPop 컬럼은 무슨 뜻이야", ["src:583", "md:데이터_활용_명세"]),
    ("데이터명세서에 버스 카드 승하차 정보 항목 설명해줘", ["spec:3-06"]),
    ("외부 LLM에 센터 데이터를 보내도 돼?", ["board:3.", "src:notice48"]),
    ("기상 데이터는 언제까지 있어?", ["md:데이터_활용_명세", "src:579"]),
    ("저장한 결과 파일은 언제 지워져?", ["md:설치_실행_매뉴얼", "board:"]),
    ("10 미만 값은 어떻게 처리해야 해?", ["src:notice48", "board:3."]),
]
HELDOUT = [
    ("센터 PC 사양이 어떻게 돼?", ["board:4."]),
    ("축제 데이터는 어디서 왔어?", ["src:761", "md:데이터_활용_명세"]),
    ("정류소 위치 정보 출처 알려줘", ["src:612", "md:데이터_활용_명세"]),
    ("반출 신청은 어떻게 해?", ["board:3.", "src:notice48"]),
    ("입도객 데이터 항목이 뭐야?", ["src:580", "src:582", "md:데이터_활용_명세"]),
    ("판단 모델이 연결 안 됐다고 나와", ["md:설치_실행_매뉴얼"]),
]


def run(cases, idx, k=3):
    rows = []
    for q, gold in cases:
        hits = idx.search(q, k=k)
        ok = any(h.doc_id.startswith(g) for h in hits for g in gold)
        rows.append({"question": q, "gold": gold, "hit": ok, "top": [h.doc_id for h in hits]})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="current")
    a = ap.parse_args()
    from app.config import ROOT
    from app.rag.corpus import load_corpus
    from app.rag.index import build_index
    idx = build_index(load_corpus(ROOT))
    out = {}
    for name, cases in (("design", DESIGN), ("heldout", HELDOUT)):
        rows = run(cases, idx)
        out[name] = {"hit_at_3": sum(r["hit"] for r in rows) / len(rows), "n": len(rows), "rows": rows}
        print(f"{name}: hit@3 {sum(r['hit'] for r in rows)}/{len(rows)}")
        for r in rows:
            print(f"   {'O' if r['hit'] else 'X'} {r['question']}  → {', '.join(t[:28] for t in r['top'])}")
    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path(f"eval/results/rag_probe_{a.tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
