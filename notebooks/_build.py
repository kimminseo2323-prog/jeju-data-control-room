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
- 일일 쿼터: **데이터별 기본 1,000회** (프로젝트 화면에서 확인). 초과하면 서버가 **HTTP 403**
- 대용량 3종(유동인구 583·와이파이 장소별 593·정류소별 버스 613)은 증설을 신청해 **5,000회 승인**(2026-11-11 확인) → `Job.daily_quota`에 반영
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
by_api = {j.api_id: j for j in JOBS.values()}
used = []
for f in Path("data/state").glob(f"quota_{today}_*.txt"):
    api = f.stem.split("_", 2)[2]
    job, n = by_api.get(api), int(f.read_text() or 0)
    quota = job.daily_quota if job else 1000
    used.append({"작업": job.name if job else "(이전 ID)", "오늘 호출 수": n, "일일 쿼터": quota, "남은 쿼터": max(0, quota - n)})
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
    ("md", """## 버스 이용(613) → 읍면동 연결
정류소별 버스 이용(613)의 정류소ID(7자리)는 정류소 기본 정보(612)의 ID(9자리)와 체계가 달라 **ID로는 하나도 겹치지 않는다**(2026-11-11 확인).
그래서 기호·공백을 뺀 정류소 이름이 612에서 **한 읍면동에만** 있을 때 그 읍면동으로 연결하고, 같은 이름이 여러 읍면동에 있으면(터미널 등) 추측하지 않고 '모호'로 뺀다."""),
    ("code", """bus = st._read("bus_station_daily")
_ = st._map_bus(bus)
m = st._bus_mapping
print(f"정류소별 버스 이용 {len(bus):,}행, 기간 {bus['baseDate'].min()} ~ {bus['baseDate'].max()}")
pd.DataFrame({"구분": ["ID로 연결", "이름으로 연결", "모호(같은 이름이 여러 읍면동)", "매칭 실패"],
              "이용자 수 비중(%)": [m["by_id"], m["by_name"], m["ambiguous_name"], m["unmatched"]]})"""),
    ("md", """**해석**: 정류소나 AP그룹이 0인 행정동은 해당 신호로 이상을 볼 수 없다 → 화면과 브리핑에 '신호 없음'으로 표시한다.
추자도(위도 33.96)는 처음 위도 범위(33.1~33.6)를 벗어나 매칭 실패로 빠졌다 → 범위를 33.1~34.0으로 넓혀 추자면 와이파이 AP그룹을 연결했다(추자면 버스 정류소는 612에 없음)."""),
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
    ("md", """# 04. 실제 데이터 이상 탐지
**데이터**: 허브 유동인구(583) 2024-04-01~2025-03-31(12개월). 끝까지 받은 달만 쓴다(아래 첫 셀에서 기간·행 수 확인).

**방법** (`app/analytics/detect.py`)
- `seasonal_z`: 같은 요일 앞뒤 4주 값의 중앙값을 기대값으로, 잔차를 MAD로 표준화한 점수
- `robust_resid`: STL(주기 7, seasonal=13, trend=29) 분해 잔차를 MAD로 표준화
- 수집되지 않은 날은 이상으로 보지 않음, 연속 이상일은 '구간'으로 묶음(3일 이상 = 지속 변화)"""),
    ("code", SETUP),
    ("code", """from app.store.cache import CacheStore
from app.analytics.detect import detect_anomalies, group_episodes
st = CacheStore("data/cache")
pop = st._read("pop_domestic")
print(f"유동인구 {len(pop):,}행, 기간 {pop['baseDate'].min()} ~ {pop['baseDate'].max()}, 날짜 {pop['baseDate'].nunique()}일")
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
    ("code", """lo, hi = pd.to_datetime(pop["baseDate"].astype(str)).agg(["min", "max"])
daily = an[an["방법"] == "seasonal_z"].groupby("날짜").size().reindex(pd.date_range(lo, hi).date, fill_value=0)
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
    ("md", """**읽은 것** (2024-04-01~2025-03-31, 43개 읍면동, 점수 3.5 기준)
- 이상 읍면동이 가장 많은 날은 추석(2024-09-16·17)과 설날(2025-01-28~30) → 여러 곳이 동시에 움직인 날은 '공휴일·연휴' 원인 후보
- 7월 말~8월 초(2024-07-31, 08-01·02)에도 20곳 이상이 함께 증가 → 공휴일이 아니므로 여름 성수기(제주 전체 동반 변화)로 본다. 이호동 07-26~29(+104%)가 대표 사례
- 점수 1위는 삼도1동 2025-03-28~30(기대 대비 +170%). 같은 날 와이파이(점수 13.7)·버스도 함께 늘어 데이터 오류로 보기는 어렵다. 기상·공휴일·축제 자료(761)에는 맞는 사건이 없다. 삼도1동을 뺀 제주 전체 와이파이도 같은 날 늘어(점수 4.1) 판정 모델은 '관광 수요 변화'(62.5%, 판단 불가 34.5%)로 보았지만, **실제 사건은 미확인**이다
- 같은 기준에서 STL 잔차(robust_resid)는 이상일을 약 3배 많이 낸다(1,237 vs 441). 가짜 이상 주입 평가에서 같은 경보 빈도로 맞추면 재현율 차이가 작아(유동인구 +2.1%p), 설명하기 쉬운 같은 요일 중앙값을 기본으로 둔다
- 한계: 1년치라 '작년 같은 달' 비교는 못 함, 시리즈 끝(2025-03-31)은 앞쪽 데이터만으로 기준선을 잡음"""),
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
→ `find_co_movements` 도구가 같은 읍면동의 다른 신호와 함께 **제주 전체 합계**도 확인하도록 바꿨다.

**보완(2026-11-11)**: 1년치로 다시 보니 삼도1동 2025-03-29 와이파이(점수 13.7)처럼 한 곳의 큰 급증이 제주 전체 합계까지 끌어올렸다. 그래서 제주 전체 합계는 **설명하려는 읍면동을 뺀 나머지 합계**로 비교한다(`tests/test_agent.py::test_island_total_excludes_the_region_itself`)."""),
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


NOTEBOOKS["06_분석보완_외국인_기간연장"] = [
    ("md", """# 06. 분석 보완 — 외국인 신호, 기간 연장, 작년 반복, 인근 읍면동, 원인 판정 대규모 평가
**배경 (2026-11-11 허브 목록·사이트 재확인)**
- 유동인구(583)·외국인 단기체류 유동인구(589)는 2026-08-31까지 있다 → 분석 기간을 2024-04~2026-08로 늘렸다
- 기상(579)·축제(761)는 2025-03까지, 입도객(580)은 2025-07까지 → 그 뒤 날짜는 해당 근거를 **'확인 불가'**로 표시한다(없다는 뜻이 아님)
- 크루즈 기항(319)은 연도별 합계, 공항·관광지 입장객은 월 단위라 일 단위 근거로 쓰지 않았다

모든 계산은 `app/` 모듈을 그대로 부른다. 노트북 01~05는 1년치(2024-04~2025-03) 단계의 기록으로 그대로 둔다."""),
    ("code", SETUP + """
import json
from app.store.cache import CacheStore
from app.agent.tools import Toolbox
st = CacheStore("data/cache"); tb = Toolbox(st, None)
pd.DataFrame([{"신호": s, "읍면동 수": len(st.regions(s)), "시작": st.island_series(s).dropna().index.min().date(), "끝": st.island_series(s).dropna().index.max().date()} for s in st.signals()])"""),
    ("md", "## 1. 근거 자료별 제공 기간 — 이 밖의 날짜는 '확인 불가'"),
    ("code", """pd.DataFrame([{"근거": k, "시작": v[0].date(), "끝": v[1].date()} for k, v in st.coverage.items()])"""),
    ("md", """## 2. 외국인 신호(허브 589)
외국인 단기체류 유동인구를 읍면동·일 단위로 합쳐 네 번째 신호로 넣었다. 국적별 값이 있어, 이상이 난 날 **어느 국적이 움직였는지** 나눠 볼 수 있다(`nationality_mix` 도구)."""),
    ("code", """fig, ax = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
for a, s, c in zip(ax, ["유동인구", "외국인"], ["#1F3A5F", "#2A7F7F"]):
    x = st.island_series(s); a.plot(x.index, x / 1e4, color=c, lw=.8); a.set_ylabel("만 명"); a.set_title(f"제주 전체 {s}", loc="left", fontsize=10)
plt.tight_layout()"""),
    ("code", """emd, day = "서귀포시 송산동", "2024-09-29"
r = tb.dispatch("nationality_mix", {"date": day, "emd": emd, "top": 3}, "R1").data
print(f"{emd} {day} 외국인 전체 변화(기대값 대비): {r['total_diff']:+,}명")
pd.DataFrame(r["top"])"""),
    ("md", "### 외국인 신호 탐지 평가 — 가짜 이상 주입 (`python -m eval.inject_eval --signal 외국인`)"),
    ("code", """rows = []
for s in ["유동인구", "와이파이", "버스", "외국인"]:
    p = Path(f"eval/results/inject_eval_{s}.json")
    if not p.exists():
        continue
    d = json.loads(p.read_text("utf-8"))
    sw = next(x for x in d["sweep"] if x["method"] == "seasonal_z" and x["threshold"] == 3.5)
    al = next(x for x in d["alarms"] if x["method"] == "seasonal_z" and x["threshold"] == 3.5)
    rows.append({"신호": s, "읍면동": d["regions"], "주입 횟수": d["trials"], "구간 적중률": sw["episode_hit"], "일 재현율": sw["day_recall"], "평소 경보(100일당)": al["alarms_per_100_days"]})
pd.DataFrame(rows)"""),
    ("md", """**읽은 것**
- 외국인 신호도 같은 탐지 방법(점수 3.5)으로 주입한 이상 구간의 40%를 잡는다. 유동인구(59%)보다 낮고 와이파이(28%)·버스(38%)와 비슷하다 — 읍면동별 외국인 수가 작아 날마다 변동이 크기 때문이다
- 평소 경보는 100일당 1.85건으로 네 신호 중 가장 적다
- 유동인구는 기간을 늘리자 평소 경보가 100일당 2.81건(1년치)에서 4.07건으로 늘었다. 2025-10 추석·개천절 7일 연휴, 2025-05 연휴, 2026-02 설처럼 실제 급증이 늘어난 것이다(1년치 결과: `eval/results/_1year/`)"""),
    ("md", """### 외국인 신호에 맞는 공휴일 근거
원인 판정 평가(5절)에서 외국인 신호는 한국 공휴일을 정답으로 둔 구간의 일치율이 55.6%(63건)로 낮았다. 판정이 틀린 것인지, **한국 공휴일이 외국인 방문의 근거가 아닌 것**인지 데이터로 확인한다.
읍면동별 급증(점수 3.5 이상) 비율을 공휴일 앞뒤 1일과 그 외 날로 나눠 비교한다."""),
    ("code", """import holidays
def surge_ratio(frame, country):
    Z = pd.concat([score_series(frame[c], "seasonal_z")[2].rename(c) for c in frame.columns if frame[c].notna().sum() > 100], axis=1)
    cal = holidays.country_holidays(country, years=range(2024, 2027))
    near = pd.Series([any((d + pd.Timedelta(days=k)).date() in cal for k in (-1, 0, 1)) for d in Z.index], index=Z.index)
    up, ok = Z >= 3.5, Z.notna()
    r1, r0 = up[near].sum().sum() / ok[near].sum().sum() * 100, up[~near].sum().sum() / ok[~near].sum().sum() * 100
    return round(r1, 2), round(r0, 2), round(r1 / r0, 1)
from app.analytics.detect import score_series
f = st._foreign.assign(d=lambda x: pd.to_datetime(x["baseDate"].astype(str)))
def frame(sig=None, nat=None):
    if sig:
        return pd.DataFrame({e: st.series(sig, e) for e in st.regions(sig)})
    return f[f["nationality"] == nat].pivot_table(index="d", columns="emd_full", values="visitPop", aggfunc="sum").reindex(pd.date_range("2024-04-01", "2026-08-31"))
rows = []
for label, fr, countries in [("내국인 유동인구", frame("유동인구"), ["KR"]), ("외국인 전체", frame("외국인"), ["KR", "CN", "JP"]),
                             ("중국 국적", frame(nat="중국"), ["KR", "CN"]), ("일본 국적", frame(nat="일본"), ["KR", "JP"])]:
    for c in countries:
        r1, r0, x = surge_ratio(fr, c)
        rows.append({"대상": label, "공휴일 국가": c, "공휴일 앞뒤 급증 비율(%)": r1, "그 외 날(%)": r0, "배수": x})
pd.DataFrame(rows)"""),
    ("md", """**읽은 것**: 한국 공휴일 앞뒤에 내국인 급증은 평소의 9배가 넘지만, 외국인 전체는 1.1배로 거의 차이가 없다. 일본인은 일본 공휴일 앞뒤에 2.3배, 중국인은 중국 공휴일 앞뒤에 1.7배다.
→ 외국인 신호를 설명할 때는 **한국 공휴일 대신 중국·일본 공휴일**을 맥락으로 넘기도록 바꿨다(`check_context(..., holiday_countries=("CN", "JP"))`, 테스트 `test_foreign_signal_uses_visitor_country_holidays_not_korean`).
이 변경은 평가 결과를 본 뒤에 한 것이라, 수정 전 결과(`eval/results/judge_eval_before_foreign_holiday.json`)도 함께 둔다."""),
    ("md", """## 3. 인근 읍면동 동반 변화
읍면동 중심점(정류소·AP 평균 좌표) 사이 거리로 가까운 3곳(15km 이내)을 이웃으로 둔다. 이웃 합계도 같이 움직였다면 '이 동네만의 일'이 아니라 '주변 일대의 흐름'일 가능성이 크다."""),
    ("code", """pd.DataFrame([{"읍면동": e, "인근(가까운 순)": ", ".join(st.neighbors(e)) or "(15km 안에 없음)"} for e in ["제주시 이호동", "서귀포시 성산읍", "제주시 추자면", "서귀포시 송산동"]])"""),
    ("md", """## 4. 작년 같은 시기 반복
기간을 늘리면서 1년 전 같은 시기(52주 전 같은 요일 ±3일)와 비교할 수 있게 됐다. 그때도 같은 방향 이상(점수 3 이상)이 있었다면 '매년 반복되는 변화일 수 있음'으로 근거에 붙인다.
2025-04 이후 이상 구간 중 몇 개에 반복 근거가 붙는지 센다."""),
    ("code", """import re
from app.analytics.detect import detect_anomalies, group_episodes
from app.analytics.context import recurrence
rows = []
for s in ["유동인구", "외국인"]:
    for emd in st.regions(s):
        x = st.series(s, emd)
        for e in group_episodes(detect_anomalies(x, threshold=3.5)):
            if e.peak.date < pd.Timestamp("2025-04-01"):
                continue
            rc = recurrence(x, e.peak.date, s)
            rows.append({"신호": s, "읍면동": emd, "가장 큰 날": e.peak.date.date(), "방향": "증가" if e.peak.score > 0 else "감소", "작년 반복": rc is not None, "작년 날짜": re.search(r"\\d{4}-\\d{2}-\\d{2}", rc.detail).group() if rc else ""})
rec = pd.DataFrame(rows)
rec.groupby("신호")["작년 반복"].agg(["sum", "count", "mean"]).round(3)"""),
    ("md", "공휴일(가장 큰 날 ±1일)과 겹치는 구간은 이미 공휴일 근거가 있다. **공휴일이 아닌데 작년에도 반복된 구간**이 이 근거가 새로 설명하는 부분이다."),
    ("code", """import holidays
kr = holidays.KR(years=range(2024, 2027))
rec["공휴일 ±1일"] = rec["가장 큰 날"].map(lambda d: any(d + pd.Timedelta(days=k) in kr for k in (-1, 0, 1)))
display(pd.crosstab([rec["신호"], rec["공휴일 ±1일"]], rec["작년 반복"], margins=True))
new = rec[~rec["공휴일 ±1일"] & rec["작년 반복"]]
new.groupby("가장 큰 날").size().sort_values(ascending=False).head(10).rename("읍면동 수")"""),
    ("md", """**읽은 것**
- 2025-04 이후 유동인구 이상 구간의 절반(367개 중 183개)에 '작년에도 그랬음' 근거가 붙는다. 공휴일이 아닌 구간에서도 절반(173개 중 87개)이며, 주로 7월 말~8월 초 휴가철 절정이다 → 그동안 공휴일로 설명되지 않던 구간에 근거가 생겼다
- 외국인 신호는 14%(341개 중 47개)만 반복된다. 외국인 급증은 해마다 같은 시기에 되풀이되는 경우가 적다
- 반복 근거는 '원인'이 아니라 '매년 반복되는 변화일 수 있음'이라는 참고 근거로만 쓴다"""),
    ("md", """## 5. 원인 판정 대규모 평가 (`python -m eval.judge_eval`)
실제 이상 구간 전체에 판정 모델(tev1:4b)을 돌려, 데이터에서 따로 확인되는 사실(공휴일·이름이 명시된 축제·강한 비바람)과 맞는지 본다.
**한계**: 정답이 판정에 넘기는 근거와 같은 자료에서 나온다 → '근거를 제대로 읽는가'를 재는 시험이지, 현장에서 확인한 원인이 아니다."""),
    ("code", """def summ(p):
    s = json.loads(Path(p).read_text("utf-8"))["summary"]
    out = {"이상 구간": s["episodes"], "정답 있는 구간": s["labeled"], "일치율": s["agree"][0], "근거 제거 시 안 고름": s["ablation_not_chosen"][0], "규칙 일치율": s["rule_agree"][0]}
    out.update({f"{k} 일치(n)": f"{v['agree'][0]} ({v['agree'][1]})" for k, v in s["by_label"].items()})
    return out
pd.DataFrame({"① 1년치·근거 문장 수정 전": summ("eval/results/_1year/judge_eval_before_label.json"),
              "② 1년치·근거 문장 수정 후": summ("eval/results/_1year/judge_eval.json"),
              "③ 기간 연장+외국인·한국 공휴일": summ("eval/results/judge_eval_before_foreign_holiday.json"),
              "④ 기간 연장+외국인·중국·일본 공휴일": summ("eval/results/judge_eval_before_nodata_fix.json"),
              "⑤ 자료 없는 신호를 '자료 없음'으로(현재)": summ("eval/results/judge_eval.json")}).T"""),
    ("md", "### 신호별 일치율 (정답이 있는 구간)"),
    ("code", """def by_signal(p):
    r = pd.DataFrame(json.loads(Path(p).read_text("utf-8"))["rows"])
    r = r[r["labels"].map(len).gt(0)]
    r["agree"] = [c in l for c, l in zip(r["choice"], r["labels"])]
    return r.groupby("signal")["agree"].agg(lambda a: f"{a.mean():.3f} ({len(a)})")
pd.DataFrame({"③ 한국 공휴일": by_signal("eval/results/judge_eval_before_foreign_holiday.json"),
              "④ 중국·일본 공휴일": by_signal("eval/results/judge_eval_before_nodata_fix.json"),
              "⑤ '자료 없음' 분리(현재)": by_signal("eval/results/judge_eval.json")})"""),
    ("code", """s = json.loads(Path("eval/results/judge_eval.json").read_text("utf-8"))["summary"]
pd.DataFrame({"정답 없음(근거 기간 안)": pd.Series(s["unlabeled_choices"]), "근거 기간 밖(전체)": pd.Series(s["outside_coverage_choices"])}).fillna(0).astype(int)"""),
    ("md", """**읽은 것**
- ① → ②: 근거 문장에 맥락 종류(날씨·공휴일 등)를 붙이자 일치율이 81.5% → 95.2%. 날씨는 23% → 54%로 여전히 낮다(13건)
- ③ 기간을 2026-08까지 늘리고 외국인 신호를 넣으니 이상 구간이 1,262개, 정답 있는 구간이 464개로 늘었다. 유동인구·버스·와이파이는 91~97%로 비슷하지만, **외국인은 55.6%**
- 2절에서 본 것처럼 한국 공휴일은 외국인 급증과 거의 관계가 없다(1.1배) → ④ 외국인 신호에는 중국·일본 공휴일을 넘기도록 바꿨다. 외국인 정답 구간이 108개로 늘었지만 일치율은 56.5%로 거의 그대로다. 중국·일본 공휴일도 급증과의 관계가 1.6~2.3배로 약해, '공휴일이 겹치면 정답은 공휴일'이라는 약한 정답 자체가 외국인에게는 잘 맞지 않는다. 이웃 읍면동이 함께 움직였으면 판정은 '관광 수요 변화'를 고르는 경우가 많았다
- ⑤ 2026-11-15 코드 점검에서, 그날 자료가 없는 신호(와이파이 2025-04 이후 등)까지 '확인한 다른 신호는 평소 수준이었다'고 판정 모델에 넘기던 잘못을 찾았다. '자료 없음(확인 불가)'으로 따로 적도록 고친 뒤 다시 돌리니 일치율이 88.2% → 83.1%로 내려갔다(1,262개 중 53개 판정이 바뀜, 주로 공휴일 → 판단 불가·관광 수요 변화). 정확한 근거로 낸 ⑤가 현재 값이다
- **평가를 본 뒤 정답이나 판정 규칙을 더 맞추지 않았다**(맞추면 평가가 의미를 잃는다). ③·④·⑤ 결과를 모두 남긴다
- 근거 제거 시험은 모든 경우 100%: 정답 근거를 지우면 그 원인을 고르지 않는다(근거 없이 원인을 지어내지 않음)
- 규칙 판정의 일치율(95.7%)이 더 높은 것은 규칙이 약한 정답을 만드는 방식과 거의 같기 때문이며, 규칙이 더 낫다는 뜻은 아니다"""),
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
