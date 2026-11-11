"""탐지 성능 평가: 실제 시계열에 가짜 이상을 넣고 찾아내는 비율(재현율)과 평소 경보 빈도를 잰다.

실행: python -m eval.inject_eval [--trials 300] [--signal 유동인구]
결과: eval/results/inject_eval_<signal>.json

- 넣는 이상: 하루 급변(1일) / 지속 변화(4일 연속), 크기 ±20·40·80%(값에 곱함)
- 넣는 날: 원래 시계열에서 점수 |z|<2인 '평범한 날'만(이미 있던 이상과 섞이지 않게), 관측 28일 이후
- 재현율: 넣은 날 중 같은 방향으로 |점수| ≥ 기준인 날의 비율 / 구간 탐지율: 넣은 구간에서 하루라도 잡힌 비율
- 평소 경보 빈도: 원래(넣기 전) 시계열에서 100일당 기준을 넘는 날 수 — 실제 연휴·성수기도 포함되므로 '오경보율'의 상한으로 읽는다
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.analytics.detect import score_series
from app.store.cache import CacheStore

METHODS = ["seasonal_z", "robust_resid"]
TYPES = {"일시 급변(1일)": 1, "지속 변화(4일)": 4}
MAGS = [0.2, 0.4, 0.8]
THRESHOLDS = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0]


def run(signal: str, trials: int, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    st = CacheStore("data/cache")
    series = {e: st.series(signal, e) for e in st.regions(signal)}
    series = {e: s for e, s in series.items() if s.dropna().shape[0] >= 60}
    base = {(e, m): score_series(s, m) for e, s in series.items() for m in METHODS}

    # 평소 경보 빈도(넣기 전)
    alarms = []
    for m in METHODS:
        zs = pd.concat([base[(e, m)][2].dropna() for e in series])
        for th in THRESHOLDS:
            alarms.append({"method": m, "threshold": th, "alarms_per_100_days": round(float((zs.abs() >= th).mean() * 100), 2),
                           "days": int(len(zs))})

    rows = []
    emds = sorted(series)
    for t in range(trials):
        e = emds[rng.integers(len(emds))]
        s = series[e]
        kind = list(TYPES)[t % len(TYPES)]
        n = TYPES[kind]
        mag = MAGS[(t // len(TYPES)) % len(MAGS)]
        sign = 1 if (t // (len(TYPES) * len(MAGS))) % 2 == 0 else -1
        z0 = base[(e, "seasonal_z")][2]
        obs = s.dropna().index
        cand = [d for d in obs[28:len(obs) - n]
                if all(dd in s.index and pd.notna(s[dd]) and abs(z0.get(dd, np.nan)) < 2
                       for dd in pd.date_range(d, periods=n, freq="D"))]
        if not cand:
            continue
        start = cand[rng.integers(len(cand))]
        days = pd.date_range(start, periods=n, freq="D")
        s2 = s.copy()
        s2[days] = s2[days] * (1 + sign * mag)
        for m in METHODS:
            _, _, z = score_series(s2, m)
            zd = z.reindex(days)
            for th in THRESHOLDS:
                hit = (zd * sign >= th)
                rows.append({"trial": t, "emd": e, "type": kind, "mag": mag, "direction": "증가" if sign > 0 else "감소",
                             "method": m, "threshold": th, "day_recall": float(hit.mean()), "episode_hit": bool(hit.any())})
    df = pd.DataFrame(rows)
    at = df[df["threshold"] == 3.5]
    by_cell = (at.groupby(["method", "type", "direction", "mag"])[["day_recall", "episode_hit"]].mean().round(3)
               .reset_index().to_dict("records"))
    sweep = df.groupby(["method", "threshold"])[["day_recall", "episode_hit"]].mean().round(3).reset_index().to_dict("records")
    return {"signal": signal, "trials": int(df["trial"].nunique()), "regions": len(series), "seed": seed,
            "alarms": alarms, "recall_at_3_5": by_cell, "sweep": sweep}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", default="유동인구")
    ap.add_argument("--trials", type=int, default=480)
    a = ap.parse_args()
    res = run(a.signal, a.trials)
    out = Path("eval/results"); out.mkdir(parents=True, exist_ok=True)
    (out / f"inject_eval_{a.signal}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    print(pd.DataFrame(res["sweep"]).merge(pd.DataFrame(res["alarms"]), on=["method", "threshold"]).to_string())
    print(pd.DataFrame(res["recall_at_3_5"]).to_string())


if __name__ == "__main__":
    main()
