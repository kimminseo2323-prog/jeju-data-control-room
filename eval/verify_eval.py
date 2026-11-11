"""검증기 평가: 실제 데이터로 만든 브리핑에 일부러 오류를 넣고 검증기가 잡는 비율을 잰다.

실행: python -m eval.verify_eval [--n 60]
결과: eval/results/verify_eval.json

오류 종류
- 숫자 변경: 근거가 달린 문장의 숫자 하나를 5~30% 바꿈(정수는 최소 2 이상 차이)
- 근거 삭제: 숫자가 있는 문장의 [Rn] 표시를 지움
- 근거 바꿔치기: [Rn]을 숫자가 없는 다른 결과 id로 바꿈
- 지어낸 숫자: 근거 id를 단 채로 결과에 없는 숫자 문장을 덧붙임
- 근거 없는 원인 단정: 탐지 결과만 인용한 원인 문장을 덧붙임
오류를 넣지 않은 원문이 통과하는 비율(정상 통과율)도 함께 잰다.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from app.agent.tools import Toolbox
from app.agent.verify import CITE, NUM, verify
from app.analytics.detect import detect_anomalies, group_episodes
from app.report.briefing import template_text
from app.store.cache import CacheStore


def briefings(n: int, seed: int = 0) -> list[tuple[str, dict]]:
    st = CacheStore("data/cache")
    tb = Toolbox(st, None)
    rng = np.random.default_rng(seed)
    cases = []
    for sig in st.signals():
        for emd in st.regions(sig):
            for e in group_episodes(detect_anomalies(st.series(sig, emd), threshold=3.5)):
                cases.append((sig, emd, e.peak.date))
    picks = [cases[i] for i in rng.choice(len(cases), size=min(n, len(cases)), replace=False)]
    out = []
    for sig, emd, day in picks:
        res = {}
        for i, (name, args) in enumerate([
            ("detect_anomalies", {"signal": sig, "emd": emd, "threshold": 3.5,
                                  "start": str((day - pd.Timedelta(days=14)).date()), "end": str((day + pd.Timedelta(days=14)).date())}),
            ("find_co_movements", {"date": str(day.date()), "emd": emd, "window": 1, "exclude_signal": sig}),
            ("check_context", {"date": str(day.date()), "emd": emd})], 1):
            res[f"R{i}"] = tb.dispatch(name, args, f"R{i}")
        out.append((template_text(res), res))
    return out


def _cited_number_lines(text: str) -> list[int]:
    lines = text.split("\n")
    return [i for i, l in enumerate(lines) if CITE.search(l) and NUM.search(CITE.sub("", l))]


def mutate(kind: str, text: str, res: dict, rng) -> str | None:
    lines = text.split("\n")
    idx = _cited_number_lines(text)
    if kind == "숫자 변경":
        if not idx:
            return None
        i = idx[rng.integers(len(idx))]
        cites = [c.span() for c in CITE.finditer(lines[i])]
        nums = [m for m in NUM.finditer(lines[i]) if not any(a <= m.start() < b for a, b in cites)]
        m = nums[rng.integers(len(nums))]
        x = float(m.group().replace(",", ""))
        f = 1 + rng.choice([-1, 1]) * rng.uniform(0.05, 0.30)
        y = x * f
        if float(x).is_integer() or "." not in m.group():
            y = round(y) if abs(round(y) - x) >= 2 else x + (2 if f > 1 else -2)
            new = f"{int(y):,}" if "," in m.group() else str(abs(int(y))).zfill(len(m.group()))  # 날짜 조각은 자릿수 유지(02→05)
        else:
            new = f"{y:,.1f}" if "," in m.group() else f"{y:.1f}"
        lines[i] = lines[i][:m.start()] + new + lines[i][m.end():]   # 일치한 그 자리의 숫자만 바꾼다(지명 속 숫자 제외)
    elif kind == "근거 삭제":
        if not idx:
            return None
        i = idx[rng.integers(len(idx))]
        lines[i] = CITE.sub("", lines[i]).rstrip()
    elif kind == "근거 바꿔치기":
        if not idx:
            return None
        i = idx[rng.integers(len(idx))]
        others = [rid for rid, r in res.items() if not re.search(r"\d", json.dumps(r.data.get("items", r.data.get("co_movements", [1])), ensure_ascii=False))]
        cur = CITE.findall(lines[i])
        others = [o for o in others if o not in cur]
        if not others:
            return None
        lines[i] = CITE.sub(f"[{others[0]}]", lines[i])
    elif kind == "지어낸 숫자":
        lines.append(f"이날 방문객은 평소보다 {int(rng.integers(1000, 90000)):,}명 더 많았습니다 [R1].")
    elif kind == "근거 없는 원인 단정":
        lines.append("이 변화의 원인은 대형 행사로 보입니다 [R1].")
    return "\n".join(lines)


KINDS = ["숫자 변경", "근거 삭제", "근거 바꿔치기", "지어낸 숫자", "근거 없는 원인 단정"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    rng = np.random.default_rng(1)
    docs = briefings(a.n)
    clean_pass = sum(verify(t, r).ok for t, r in docs)
    rows = []
    for k in KINDS:
        for t, r in docs:
            m = mutate(k, t, r, rng)
            if m is None or m == t:
                continue
            rows.append({"kind": k, "caught": not verify(m, r).ok})
    df = pd.DataFrame(rows)
    summary = {"briefings": len(docs), "clean_pass_rate": round(clean_pass / len(docs), 3),
               "catch_rate": df.groupby("kind")["caught"].agg(["mean", "count"]).round(3).reset_index()
               .rename(columns={"mean": "catch_rate", "count": "n"}).to_dict("records")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    out = Path("eval/results"); out.mkdir(parents=True, exist_ok=True)
    (out / "verify_eval.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
