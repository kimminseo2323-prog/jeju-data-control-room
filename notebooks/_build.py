"""노트북 생성·실행기. 실행: python notebooks/_build.py [노트북 번호...]

각 노트북은 app/ 모듈을 불러 결과만 보여 준다(로직 중복 없음). 허브 API는 호출하지 않는다(쿼터 보호).
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

SETUP = """import sys, os
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import pandas as pd
pd.set_option("display.max_colwidth", 60)
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False"""

NOTEBOOKS: dict[str, list[tuple[str, str]]] = {}

NOTEBOOKS["01_데이터수집"] = [
    ("md", """# 01. 제주데이터허브 데이터 수집
**목적**: 이상 신호 탐지에 쓸 일 단위 신호(유동인구·와이파이·버스)와 맥락(기상·입도객·행사), 위치 기준(정류소·AP)을 허브 Open API로 받는다.

**허브 API 규칙 (2026-11-10 확인)**
- 호출: `open.jejudatahub.net/api/proxy/{데이터별 ID}/{프로젝트키}` — 키는 `.env`에만 저장
- 페이지: `number`, `limit`(최대 100) → 응답 `{totCnt, hasMore, data}`
- 일일 쿼터: **데이터별 1,000회** (프로젝트 화면에서 확인). 초과하면 서버가 **HTTP 403**
- 수집기(`app/ingest/hub_client.py`)는 쿼터를 데이터별로 세고, 멈춘 페이지부터 다음 날 이어받는다

**수집 중 발견한 문제와 해결**
| 문제 | 원인 | 해결 |
|---|---|---|
| 와이파이 AP그룹별 일일(593) 403 | 2020년 기술문서의 API ID가 바뀜 | 허브 상세 페이지의 현재 ID로 교체 → 1,420/1,420행 확인 |
| AP 정보(618) 실행마다 행 구성이 다름 | 페이지 정렬이 고정되지 않음(3,049행 중 고유 1,960 / 1,838) | 같은 요청을 반복해 고유 키로 합침 → 8회 만에 2,615개로 수렴 |
| 쿼터 초과 시 403을 오류로 재시도 | 403의 의미 미확인 | 403 = 쿼터 초과로 처리, 재시도하지 않고 이어받기 지점 저장 |
| 유동인구(583)·정류소별 버스(613) | 같은 날 2회 받아 비교 | 고유 키 수 = totCnt(688, 2,012) → 정렬 안정 확인 |"""),
    ("code", SETUP),
    ("md", "## 수집 작업 정의 (`app/ingest/jobs.py`)"),
    ("code", """from app.ingest.jobs import JOBS
pd.DataFrame([{"작업": j.name, "허브 데이터": j.hub_data_id, "데이터명": j.title, "방식": j.mode, "고정 조건": j.extra or ""} for j in JOBS.values()])"""),
    ("md", "## 수집 계획 (`app/ingest/plan.py`) — 주 분석 기간 2024-04-01 ~ 2025-03-31, 저비용 신호는 최근까지"),
    ("code", """from app.ingest.plan import PLAN
pd.DataFrame(PLAN, columns=["작업", "시작", "끝"])"""),
    ("md", "## 수집 결과 (캐시 파일)"),
    ("code", """rows = []
for p in sorted(Path("data/cache").glob("*.parquet")):
    d = pd.read_parquet(p)
    date_col = next((c for c in ["baseDate", "dtYearMonth"] if c in d.columns), None)
    rng = (str(d[date_col].astype(str).min()), str(d[date_col].astype(str).max())) if date_col else ("-", "-")
    rows.append({"파일": p.stem, "행 수": len(d), "열 수": d.shape[1], "기간 시작": rng[0], "기간 끝": rng[1]})
pd.DataFrame(rows)"""),
    ("md", "## 진행 중·남은 수집 (데이터별 오늘 사용한 호출 수)"),
    ("code", """from app.ingest.jobs import JOBS
import datetime as dt
today = dt.date.today().strftime("%Y%m%d")
by_api = {j.api_id: j.name for j in JOBS.values()}
used = []
for f in Path("data/state").glob(f"quota_{today}_*.txt"):
    api = f.stem.split("_", 2)[2]
    used.append({"작업": by_api.get(api, "(이전 ID)"), "오늘 호출 수": int(f.read_text() or 0), "남은 쿼터": max(0, 1000 - int(f.read_text() or 0))})
pd.DataFrame(used).sort_values("오늘 호출 수", ascending=False).reset_index(drop=True)"""),
]

NOTEBOOKS["02_위치매핑_품질"] = [
    ("md", """# 02. 위치 매핑과 데이터 품질
**목적**: 와이파이 AP그룹·버스 정류소를 행정동(읍면동 43개) 단위로 묶어 유동인구와 같은 단위에서 비교한다.

**방법** (`app/store/geo.py`, `app/store/cache.py`)
1. 주소 문자열에서 행정동 이름을 찾는다 (예: `서귀포시 성산읍 성산리` → `서귀포시 성산읍`)
2. 법정동만 있는 주소(예: `일도일동`)는 추측하지 않고, 주소로 확정된 **가장 가까운 정류소의 행정동**(2km 이내)을 쓴다
3. 둘 다 실패하면 버리지 않고 '매칭 실패'로 따로 센다"""),
    ("code", SETUP),
    ("code", """from app.store.cache import CacheStore
st = CacheStore("data/cache")
s = st.stations
pd.DataFrame({"구분": ["주소로 매칭", "가까운 정류소로 매칭", "매칭 실패(제주 밖·2km 초과)"],
              "정류소 수": [(s["method"] == "address").sum(), (s["method"] == "nearest").sum(), st._station_unmatched]})"""),
    ("code", """g = st.ap_groups
print(f"AP그룹 {len(g)}개 매핑, 매칭 실패 그룹 {len(st._ap_unmatched_groups)}개, 정류소 행정동 {s['emd'].nunique()}개 · AP그룹 행정동 {g['emd'].nunique()}개 (전체 43개)")
ax = g["category"].value_counts().plot.barh(figsize=(7, 5), color="#2A7F7F", title="와이파이 AP그룹 카테고리")
ax.invert_yaxis(); plt.tight_layout()"""),
    ("md", "## 행정동별 커버리지 — 정류소·AP그룹 수, 가장 가까운 기상관측소"),
    ("code", """from app.store.geo import EMD_43
cov = pd.DataFrame({"행정동": EMD_43})
cov["정류소"] = cov["행정동"].map(s["emd"].value_counts()).fillna(0).astype(int)
cov["AP그룹"] = cov["행정동"].map(g["emd"].value_counts()).fillna(0).astype(int)
cov["관광지 AP그룹"] = cov["행정동"].map(g[g["category"] == "관광지"]["emd"].value_counts()).fillna(0).astype(int)
cov["기상관측소"] = cov["행정동"].map(st.station_of_emd)
cov"""),
    ("md", "**해석**: 정류소나 AP그룹이 0인 행정동은 해당 신호로 이상을 볼 수 없다 → 화면과 브리핑에 '신호 없음'으로 표시한다."),
]

NOTEBOOKS["03_로컬판단모델_tev1"] = [
    ("md", """# 03. 로컬 판단 모델(tev1) 사전 실험
**왜 로컬 모델인가**: 센터 데이터는 외부로 보낼 수 없고(게시판 답변), 외부 LLM API는 비용이 든다 → 센터 PC 안에서 무료로 도는 판단 모델을 기본으로 쓴다.

**tev1**: Together AI의 판단(decision) 모델(Qwen3.5 미세조정, 0.8B·4B), Ollama `/v1/systemone`. 보기 중 고르기·참거짓·등급 + **보기별 확률**을 돌려준다. 라이선스 Apache 2.0(모델)·MIT(open-jev).

**실험**: 정답을 정해 둔 한국어 원인 판정 10건(`eval/tev1_probe.py`) — 기상·연휴·행사·관광 수요·데이터 오류·판단 불가. CPU 측정은 GPU를 숨긴 별도 Ollama 서버로 했다(요청 옵션 `num_gpu:0`은 이 API에서 무시됨)."""),
    ("code", SETUP),
    ("code", """import json
res = []
for p in sorted(Path("eval/results").glob("tev1_probe_*.json")):
    j = json.loads(p.read_text("utf-8"))
    sm = j["summary"]
    res.append({"모델": sm["model"], "장치": "CPU만" if sm["cpu_only"] else "GPU", "정답률": sm["accuracy"],
                "첫 호출(초)": sm["sec_first"], "1건당 중앙값(초)": sm["sec_median_rest"], "파일": p.name})
pd.DataFrame(res)"""),
    ("md", "※ `_cpu` 결과는 GPU를 숨긴 별도 Ollama 서버(포트 11501)에서 잰 값, `_gpu`는 RTX 4070 Ti에서 잰 값이다."),
    ("code", """j = json.loads(Path("eval/results/tev1_probe_tev1_4b_cpu.json").read_text("utf-8"))
pd.DataFrame([{"정답": r["gold"], "예측": r["pred"], "확신도": round(r["confidence"], 2), "초": r["seconds"], "사례": r["state"][:50]} for r in j["rows"]])"""),
    ("md", """**결론**: 4B를 기본 판단 모델로 채택(GPU·CPU 모두 10/10, CPU 1건 약 4초). 0.8B는 '판단 불가'로 쏠려 부적합.
**한계**: 단서가 분명한 손수 만든 10건 → 실제 성능은 가짜 이상 주입 평가에서 규칙 기반·외부 LLM과 비교해 다시 잰다. 센터 PC(i7-8700) 속도는 미확인."""),
]


NOTEBOOKS["04_이상탐지_실데이터"] = [
    ("md", """# 04. 실제 데이터 이상 탐지 (수집 중간 결과)
**데이터**: 허브 유동인구(583) 2024-04-01~07-31 — 쿼터 때문에 끝까지 받은 달만 사용(4개월, 83,935행 = 122일×688행). 나머지 기간은 수집이 끝나면 같은 코드로 다시 실행한다.

**방법** (`app/analytics/detect.py`)
- `seasonal_z`: 같은 요일 앞뒤 4주 값의 중앙값을 기대값으로, 잔차를 MAD로 표준화한 점수
- `robust_resid`: STL(주기 7, seasonal=13, trend=29) 분해 잔차를 MAD로 표준화
- 수집되지 않은 날은 이상으로 보지 않음, 연속 이상일은 '구간'으로 묶음(3일 이상 = 지속 변화)"""),
    ("code", SETUP),
    ("code", """from app.store.cache import CacheStore
from app.analytics.detect import detect_anomalies, group_episodes
st = CacheStore("data/cache")
rows, eps = [], []
for emd in st.regions("유동인구"):
    s = st.series("유동인구", emd)
    for m in ["seasonal_z", "robust_resid"]:
        found = detect_anomalies(s, method=m, threshold=3.5)
        rows += [{"읍면동": emd, "방법": m, "날짜": a.date.date(), "기대 대비(%)": round(a.pct * 100, 1), "점수": round(a.score, 1)} for a in found]
        eps += [{"읍면동": emd, "방법": m, "시작": e.start.date(), "끝": e.end.date(), "일수": e.days, "유형": e.kind,
                 "최대일": e.peak.date.date(), "기대 대비(%)": round(e.peak.pct * 100, 1), "점수": round(e.peak.score, 1)} for e in group_episodes(found)]
an, ep = pd.DataFrame(rows), pd.DataFrame(eps)
print(f"읍면동 {an['읍면동'].nunique()}곳 · 방법별 이상일:", an.groupby("방법").size().to_dict(), "· 방법별 구간:", ep.groupby("방법").size().to_dict())
both = an.pivot_table(index=["읍면동", "날짜"], columns="방법", values="점수").dropna()
print("두 방법이 모두 잡은 이상일:", len(both))"""),
    ("md", "## 이상일이 많이 겹친 날 — 여러 읍면동이 동시에 움직인 날은 제주 전체 요인(연휴·성수기) 가능성"),
    ("code", """top_days = an[an["방법"] == "seasonal_z"]["날짜"].value_counts().head(8).rename_axis("날짜").reset_index(name="이상 읍면동 수")
from app.analytics.context import KR_HOLIDAYS
top_days["공휴일"] = top_days["날짜"].map(lambda d: KR_HOLIDAYS.get(d, ""))
top_days"""),
    ("code", """daily = an[an["방법"] == "seasonal_z"].groupby("날짜").size().reindex(pd.date_range("2024-04-01", "2024-07-31").date, fill_value=0)
ax = daily.plot(figsize=(10, 3), color="#1F3A5F", title="날짜별 이상 읍면동 수(seasonal_z, 점수 3.5 이상)")
ax.set_ylabel("읍면동 수"); plt.tight_layout()"""),
    ("md", "## 점수가 큰 이상 구간 상위 10개 (seasonal_z)"),
    ("code", """ep[ep["방법"] == "seasonal_z"].sort_values("점수", key=abs, ascending=False).head(10).reset_index(drop=True)"""),
    ("md", "## 예시: 제주시 이호동 — 실제 값과 기대값"),
    ("code", """from app.analytics.detect import score_series
s = st.series("유동인구", "제주시 이호동"); _, exp, z = score_series(s, "seasonal_z")
fig, ax = plt.subplots(figsize=(10, 3.2))
ax.plot(s.index, s.values, color="#1F3A5F", label="실제(방문인구 합)"); ax.plot(exp.index, exp.values, ":", color="#9AA5B1", label="기대값")
hit = z[z.abs() >= 3.5].dropna(); ax.scatter(hit.index, s.reindex(hit.index), color="#B5473A", zorder=3, label="이상일")
ax.legend(); plt.tight_layout()"""),
    ("md", """**읽은 것**
- 5/5~5/6(어린이날·대체공휴일)과 6/7(현충일 다음 날인 금요일)에 여러 읍면동이 동시에 증가 → '공휴일·연휴' 원인 후보
- 7월 말 이호동·애월읍·한림읍 등 해변 지역의 여러 날 연속 증가 → '지속 변화'(여름 성수기 시작) — 하루짜리 급변과 구분해 보고
- 두 방법이 잡는 날이 다르다 → 가짜 이상 주입 평가로 어느 쪽을 기본으로 쓸지 정한다(Task 9)
- 한계: 4개월치라 연 단위 계절성은 반영하지 못함, 시리즈 끝(7/31)은 앞쪽 데이터만으로 기준선을 잡음"""),
]


NOTEBOOKS["05_원인근거_로컬에이전트"] = [
    ("md", """# 05. 원인 근거 보강과 로컬 에이전트(질문하기)
**목적**
1. '판단 불가'가 많던 여러 날 연속 증가(지속 변화)에 쓸 **근거**를 데이터에서 찾는다
2. 판정 모델(tev1)에 근거를 **어떤 형태로** 넘겨야 하는지 실험한다
3. 외부 LLM 없이 질문에 답하는 **로컬 에이전트**를 만들고, 질문 분류 성능을 평가한다

모든 계산은 `app/` 모듈을 그대로 부른다. 판정 모델은 이 PC의 Ollama(`127.0.0.1:11500`)에서 돈다."""),
    ("code", SETUP + """
from app.store.cache import CacheStore
from app.agent.tools import Toolbox
st = CacheStore("data/cache"); tb = Toolbox(st, None)
print("유동인구 기간:", st.island_series("유동인구").dropna().index.min().date(), "~", st.island_series("유동인구").dropna().index.max().date())"""),
    ("md", """## 1. 근거 후보 ① 월별 입도객 — 성수기·비수기 표시
방문목적별 입도객(허브 580)을 월 합계로 만들고, 주변 12개월 평균보다 ±5% 이상이면 성수기/비수기로 표시한다(본 서비스 임의 기준)."""),
    ("code", """from app.analytics.context import season_index, SEASON_PCT
v = st.visitors
tbl = pd.DataFrame({"입도객(만 명)": (v / 1e4).round(1), "주변 12개월 평균 대비(%)": [None if season_index(v, m) is None else round(season_index(v, m), 1) for m in v.index]})
tbl["표시"] = tbl["주변 12개월 평균 대비(%)"].map(lambda x: "" if x is None or pd.isna(x) or abs(x) < SEASON_PCT else ("성수기" if x > 0 else "비수기"))
tbl.index = tbl.index.strftime("%Y-%m"); tbl"""),
    ("md", """**읽은 것**: 2024년 7월은 +1.7%로 성수기 기준에 못 미친다. 7월 말 급증은 **한 달 안에서** 일어난 변화라 월 합계로는 보이지 않는다.
허브 데이터 목록에서 일별 입도객을 찾아봤지만 없었다(2026-11-11 확인) → 다른 일 단위 근거가 필요하다."""),
    ("md", """## 2. 근거 후보 ② 제주 전체 합계 — 이 지역만의 변화인가, 섬 전체의 흐름인가
43개 읍면동을 더한 '제주 전체' 시계열에도 같은 탐지 방법을 적용한다."""),
    ("code", """from app.analytics.detect import score_series
tot = st.island_series("유동인구"); _, ex, z = score_series(tot, "seasonal_z")
fig, ax = plt.subplots(figsize=(10, 3.2))
ax.plot(tot.index, tot / 1e4, color="#1F3A5F", label="제주 전체 유동인구(만 명)"); ax.plot(ex.index, ex / 1e4, ":", color="#9AA5B1", label="기대값")
hit = z[z >= 3].dropna(); ax.scatter(hit.index, tot.reindex(hit.index) / 1e4, color="#B5473A", zorder=3, label="점수 3 이상")
ax.legend(); plt.tight_layout()
pd.DataFrame({"제주 전체": tot, "기대값": ex.round(0), "점수": z.round(2)}).loc["2024-07-24":"2024-08-02"]"""),
    ("md", """**읽은 것**: 7월 말에는 섬 전체 유동인구도 크게 늘었다 → 해변 지역의 증가는 '섬 전체 관광 수요 증가'와 함께 움직인 것으로 볼 수 있다.
→ `find_co_movements` 도구가 같은 읍면동의 다른 신호와 함께 **제주 전체 합계**도 확인하도록 바꿨다."""),
    ("md", """## 3. 판정 모델에 근거를 넘기는 형태 실험 (이호동 7월 말 사례)
같은 근거를 ① JSON 그대로 ② 한국어 문장 ③ 영어 문장으로 넘겨 비교한다."""),
    ("code", """import json, requests
from app.llm.judge import CAUSES, CAUSE_KO, evidence_text
ev = {"anomaly": {"emd": "제주시 이호동", "signal": "유동인구", "date": "2024-07-28", "pct": 103.8, "kind": "지속 변화", "days": 4},
      "context": [], "co_movements": [{"signal": "제주 전체 유동인구", "date": "2024-07-29", "z": 4.83, "direction": "up"}]}
en = ("Anomaly: domestic visitor population in Iho-dong (Jeju City) was above its normal same-weekday level for 4 consecutive days, "
      "peaking at +103.8% vs expected.\\nEvidence 1 (co-movement): the island-wide total visitor population of Jeju also rose sharply (z=4.83, up); "
      "this is not local.\\nEvidence 2 (context): no severe weather, no public holiday, no registered event.")
def ask(state):
    body = {"model": "tev1:4b", "state": state, "questions": {"cause": {"type": "choice",
            "instructions": "Which listed cause best explains this anomaly in Jeju tourism/transport data? Judge only from the given evidence.", "criteria": CAUSES}}}
    a = requests.post("http://127.0.0.1:11500/v1/systemone", json=body, timeout=120).json()["answers"]["cause"]
    return CAUSE_KO[a["choice"]], round(a["probabilities"][a["choice"]], 2), round(a["probabilities"].get("tourism_demand", 0), 2)
print(evidence_text(ev))
pd.DataFrame([("① JSON", *ask(json.dumps(ev, ensure_ascii=False))), ("② 한국어 문장(채택)", *ask(evidence_text(ev))), ("③ 영어 문장", *ask(en))],
             columns=["입력 형태", "판정", "판정 확률", "'관광 수요 변화' 확률"])"""),
    ("md", """**읽은 것**: JSON을 그대로 넘기면 '제주 전체'라는 근거의 뜻을 놓치고 '판단 불가'로 답한다. 문장으로 풀어 주면 '관광 수요 변화'로 판정한다.
사전 실험(노트북 03)은 처음부터 문장형으로 했으므로, **실제 판정 경로도 문장형(`evidence_text`)으로 맞췄다**. 영어가 약간 더 높지만 근거 원문(기상·행사 이름)이 한국어라 한국어 문장을 채택했다."""),
    ("md", "## 4. 실제 이상 구간 상위 15개: 규칙 기반 vs tev1 판정"),
    ("code", """from app.analytics.detect import detect_anomalies, group_episodes
from app.llm.judge import judge_cause, rule_judge
eps = sorted(((abs(e.peak.score), emd, e) for emd in st.regions("유동인구")
              for e in group_episodes(detect_anomalies(st.series("유동인구", emd), threshold=3.5))), key=lambda x: -x[0])[:15]
rows = []
for _, emd, e in eps:
    day = str(e.peak.date.date())
    co = tb.dispatch("find_co_movements", {"date": day, "emd": emd, "window": 1, "exclude_signal": "유동인구"}, "R2").data["co_movements"]
    cx = tb.dispatch("check_context", {"date": day, "emd": emd}, "R3").data["items"]
    evd = {"anomaly": {"emd": emd, "signal": "유동인구", "date": day, "pct": round(e.peak.pct * 100, 1), "kind": e.kind, "days": e.days}, "context": cx, "co_movements": co}
    j = judge_cause(evd)
    rows.append({"읍면동": emd, "구간": f"{e.start.date()}~{e.end.date()}", "유형": e.kind, "기대 대비(%)": round(e.peak.pct * 100), "맥락": ", ".join(c["kind"] for c in cx),
                 "동반 변화": ", ".join(c["signal"] for c in co), "규칙": CAUSE_KO[rule_judge(evd).choice], "tev1:4b": CAUSE_KO[j.choice], "확률": round(j.probabilities.get(j.choice, 0), 2)})
cmp = pd.DataFrame(rows); print("규칙과 tev1 일치:", (cmp["규칙"] == cmp["tev1:4b"]).sum(), "/", len(cmp)); cmp"""),
    ("md", """**읽은 것**
- 추석 연휴(2024-09-14~18) 구간은 공휴일 근거가 있어 '공휴일·연휴', 7월 말 해변 지역은 제주 전체 동반 증가 근거로 '관광 수요 변화'로 판정된다
- 근거가 없는 하루짜리 급변(일도1동 5/31)은 '판단 불가'(약 0.95) — 근거 없이 원인을 지어내지 않는다
- 이 표에서는 규칙과 tev1이 모두 같았다. 둘이 갈리는 사례와 정답 기준 평가는 가짜 이상 주입 평가(노트북 06 예정)에서 다룬다"""),
    ("md", """## 5. 로컬 에이전트(질문하기 탭)
질문 분류는 tev1, 지역·날짜·신호는 규칙으로 추출, 계산은 정해진 도구 흐름, 답변 숫자는 검증기를 통과해야만 표시된다(외부 LLM 없음)."""),
    ("code", """from app.agent.local import answer, INTENT_KO
from app.rag.corpus import load_corpus
from app.rag.index import build_index
tba = Toolbox(st, build_index(load_corpus(ROOT)))
for q in ["7월에 유동인구가 이상하게 많았던 곳 알려줘", "이호동 7월 28일에 사람이 왜 이렇게 많았어?", "반출 가능한 결과물 기준이 뭐야?", "오늘 점심 메뉴 추천해줘"]:
    r = answer(q, tba)
    print(f"Q. {q}\\n   분류={INTENT_KO[r.intent]} ({r.router}) · 검증={'통과' if r.verified else '미통과'} · 도구 {[x.tool for x in r.results.values()]}")
    print("   " + r.final_text.replace("\\n", "\\n   ")[:700], "\\n")"""),
    ("md", """## 6. 질문 분류 평가 (`python -m eval.intent_probe`)
- 설계용 24문항: 결합 방식을 정할 때 본 질문
- **평가 전용 12문항**: 결합 방식을 정하기 *전에* 따로 적어 커밋해 둔 질문(설계에 쓰지 않음)"""),
    ("code", """res = {m: json.load(open(f"eval/results/intent_probe_{m.replace(':', '_')}.json", encoding="utf-8")) for m in ["tev1:4b", "tev1:0.8b"]}
pd.DataFrame([{"모델": m, "세트": k, "문항": r["summary"][k]["n"], "키워드 규칙": r["summary"][k]["rule_accuracy"],
               "모델 단독": r["summary"][k]["model_accuracy"], "모델+규칙 보완": r["summary"][k]["hybrid_accuracy"], "응답(초, 중앙값)": r["summary"][k]["sec_median"]}
              for m, r in res.items() for k in ["design", "heldout"]])"""),
    ("md", """**읽은 것**
- 키워드 규칙은 설계용 질문에서 92%였지만 **처음 보는 질문에서 33%** — 내가 쓴 질문에 맞춰진 규칙은 일반화되지 않는다
- **tev1:4b는 처음 보는 질문에서도 83%** (0.8b는 58%) → 질문 분류는 4B 모델에 맡기고, 연결이 안 될 때만 규칙을 쓴다
- 모델+규칙 보완은 평가 전용 세트에서 모델 단독과 같았다(이득·손해 없음)
- 한계: 문항 수가 적고(36개) 질문을 내가 썼다 → 실제 사용자 질문으로 재평가 필요"""),
]


def build(name: str, cells: list[tuple[str, str]]) -> Path:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "jeju-venv", "display_name": "Python (jeju venv)", "language": "python"}
    nb.cells = [nbformat.v4.new_markdown_cell(src) if kind == "md" else nbformat.v4.new_code_cell(src) for kind, src in cells]
    NotebookClient(nb, timeout=600, kernel_name="jeju-venv", resources={"metadata": {"path": str(HERE)}}).execute()
    out = HERE / f"{name}.ipynb"
    nbformat.write(nb, out)
    return out


if __name__ == "__main__":
    wanted = sys.argv[1:]
    for name, cells in NOTEBOOKS.items():
        if not wanted or any(name.startswith(w) for w in wanted):
            print("built", build(name, cells))
