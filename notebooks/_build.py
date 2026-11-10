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
