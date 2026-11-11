"""제주 데이터 관제실 — 화면. 실행: streamlit run app/ui/app.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from app.agent.local import INTENT_KO, answer
from app.agent.loop import AgentRun
from app.agent.tools import Toolbox
from app.agent.verify import verify
from app.analytics.detect import group_episodes, score_series, detect_anomalies
from app.llm.judge import CAUSE_KO, DEFAULT_HOST, DEFAULT_MODEL, evidence_text, judge_cause
from app.rag.corpus import load_corpus
from app.rag.index import build_index
from app.report.briefing import ResultStore, render_briefing, template_text
from app.store.cache import CacheStore

st.set_page_config(page_title="제주 데이터 관제실", page_icon="📡", layout="wide")
NAVY, TEAL, RED = "#1F3A5F", "#2A7F7F", "#B5473A"


@st.cache_resource
def get_store() -> CacheStore:
    return CacheStore(ROOT / "data" / "cache")


@st.cache_resource
def get_index():
    return build_index(load_corpus(ROOT))


@st.cache_resource
def get_toolbox() -> Toolbox:
    return Toolbox(get_store(), get_index())


@st.cache_data(show_spinner="이상 신호 계산 중…")
def scan(signal: str, method: str, threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    store = get_store()
    zs, eps = {}, []
    for emd in store.regions(signal):
        s = store.series(signal, emd)
        scored = score_series(s, method)
        if scored is None:
            continue
        zs[emd] = scored[2]
        for e in group_episodes(detect_anomalies(s, method=method, threshold=threshold)):
            eps.append({"읍면동": emd, "시작": e.start.date(), "끝": e.end.date(), "일수": e.days, "유형": e.kind,
                        "방향": "증가" if e.direction == "up" else "감소", "최대일": e.peak.date.date(),
                        "기대 대비(%)": round(e.peak.pct * 100, 1), "점수": round(e.peak.score, 1)})
    z = pd.DataFrame(zs).T.sort_index()
    ep = pd.DataFrame(eps)
    if not ep.empty:
        # 점수(평소 변동폭 대비 크기) 순 — 비율 순으로 정렬하면 인구가 적은 곳(추자면 등)이 과하게 위로 옴
        ep = ep.reindex(ep["점수"].abs().sort_values(ascending=False).index).reset_index(drop=True)
    return z, ep


def judge_status() -> str:
    try:
        v = requests.get(f"{DEFAULT_HOST}/api/version", timeout=2).json()["version"]
        return f"연결됨 · {DEFAULT_MODEL} (Ollama {v})"
    except Exception:
        return "연결 안 됨 → 규칙 기반 판정"


# ---------------- sidebar ----------------
store = get_store()
with st.sidebar:
    st.markdown("### 📡 제주 데이터 관제실")
    signals = store.signals()
    signal = st.selectbox("신호", signals, index=0)
    method = st.radio("탐지 방법", ["seasonal_z", "robust_resid"],
                      format_func=lambda m: {"seasonal_z": "같은 요일 중앙값 기준", "robust_resid": "STL 분해 잔차"}[m])
    threshold = st.slider("민감도(점수 기준, 높을수록 엄격)", 2.5, 6.0, 3.5, 0.5)
    delete_on_exit = st.toggle("세션 종료 시 저장 결과 삭제", value=True, help="센터 퇴실 시 삭제 원칙에 맞춘 기본값")
    st.caption(f"원인 판정 모델: {judge_status()}")

q = store.quality()
z, episodes = scan(signal, method, threshold)

st.markdown(f"## {signal} 이상 신호 관제판")
c1, c2, c3, c4 = st.columns(4)
c1.metric("데이터 기준일", q["as_of"].get(signal, "-"))
c2.metric("읍면동", f"{len(z)}곳")
c3.metric("이상 구간", f"{len(episodes)}개")
c4.metric("지속 변화 구간", f"{int((episodes['유형'] == '지속 변화').sum()) if not episodes.empty else 0}개")

tab_board, tab_detail, tab_ask, tab_quality = st.tabs(["관제판", "상세 분석·브리핑", "질문하기", "데이터 품질"])

with tab_board:
    if z.empty:
        st.info("이 신호는 아직 분석할 만큼 수집되지 않았습니다.")
    else:
        zc = z.clip(-6, 6)
        fig = px.imshow(zc, aspect="auto", color_continuous_scale=[[0, "#2166AC"], [0.5, "#F7F7F7"], [1, "#B2182B"]],
                        zmin=-6, zmax=6, labels={"color": "점수"})
        fig.update_layout(height=max(420, 16 * len(zc)), margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("빨강 = 평소(같은 요일 기준선)보다 많음, 파랑 = 적음. 회색 빈칸 = 수집되지 않은 날(이상으로 보지 않음).")
        st.markdown("#### 이상 구간 (평소 변동폭 대비 점수가 큰 순)")
        st.dataframe(episodes, use_container_width=True, hide_index=True, height=360)

with tab_detail:
    if episodes.empty:
        st.info("선택할 이상 구간이 없습니다.")
    else:
        labels = [f"{r['읍면동']} · {r['최대일']} · {r['유형']} · {r['방향']} {abs(r['기대 대비(%)'])}%" for _, r in episodes.iterrows()]
        pick = st.selectbox("이상 구간 선택", range(len(labels)), format_func=lambda i: labels[i])
        row = episodes.iloc[pick]
        emd, day = row["읍면동"], pd.Timestamp(row["최대일"])

        s = store.series(signal, emd)
        _, expected, zz = score_series(s, method)
        fig = go.Figure()
        fig.add_scatter(x=s.index, y=s.values, name="실제", line=dict(color=NAVY))
        fig.add_scatter(x=expected.index, y=expected.values, name="기대값(기준선)", line=dict(color="#9AA5B1", dash="dot"))
        an = zz[zz.abs() >= threshold].dropna()
        fig.add_scatter(x=an.index, y=s.reindex(an.index), mode="markers", name="이상일", marker=dict(color=RED, size=9))
        fig.add_vrect(x0=pd.Timestamp(row["시작"]) - pd.Timedelta(hours=12), x1=pd.Timestamp(row["끝"]) + pd.Timedelta(hours=12),
                      fillcolor=RED, opacity=0.08, line_width=0)
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

        tb = get_toolbox()
        res = {}
        for i, (name, args) in enumerate([
            ("detect_anomalies", {"signal": signal, "emd": emd, "method": method, "threshold": threshold,
                                  "start": str((day - pd.Timedelta(days=14)).date()), "end": str((day + pd.Timedelta(days=14)).date())}),
            ("find_co_movements", {"date": str(day.date()), "emd": emd, "window": 1, "exclude_signal": signal}),
            ("check_context", {"date": str(day.date()), "emd": emd}),
        ], 1):
            res[f"R{i}"] = tb.dispatch(name, args, f"R{i}")

        left, right = st.columns([1, 1])
        with left:
            st.markdown("#### 같은 날 맥락")
            items = res["R3"].data["items"]
            st.write("\n".join(f"- {it['detail']}" for it in items) if items else "- 기상·공휴일·행사·성수기 기록 없음")
            st.markdown("#### 다른 신호·제주 전체 동반 변화")
            co = res["R2"].data["co_movements"]
            st.write("\n".join(f"- {c['signal']} {c['date']} 점수 {c['z']}" for c in co) if co else
                     f"- 확인한 신호({', '.join(res['R2'].data['checked'])}) 중 동반 변화 없음")
        with right:
            st.markdown("#### 원인 후보 판정")
            evidence = {"anomaly": {"emd": emd, "signal": signal, "date": str(day.date()), "pct": float(row["기대 대비(%)"]),
                                    "kind": row["유형"], "days": int(row["일수"])},
                        "context": items, "co_movements": co}
            with st.expander("판정 모델에 넘긴 근거(이 내용만 보고 판단)"):
                st.text(evidence_text(evidence))
            if st.button("원인 판정 실행", type="primary"):
                with st.spinner("판정 중…"):
                    st.session_state["judge"] = (labels[pick], judge_cause(evidence))
            if st.session_state.get("judge", (None,))[0] == labels[pick]:
                j = st.session_state["judge"][1]
                st.markdown(f"**{CAUSE_KO[j.choice]}** · 확신도 {j.level} ({j.probabilities.get(j.choice, 0):.0%}) · `{j.backend}`")
                if j.note:
                    st.caption(j.note)
                pr = pd.DataFrame({"원인": [CAUSE_KO[k] for k in j.probabilities], "확률": list(j.probabilities.values())}).sort_values("확률")
                st.plotly_chart(px.bar(pr, x="확률", y="원인", orientation="h", height=240).update_layout(margin=dict(l=0, r=0, t=0, b=0)),
                                use_container_width=True)

        st.markdown("#### 브리핑")
        text = template_text(res)
        v = verify(text, res)
        run = AgentRun(f"{emd} {signal} {row['최대일']} 이상 구간", [], results=res, final_text=text, verified=v.ok)
        st.markdown(("✅ 검증 통과" if v.ok else "⚠️ 검증 미통과") + " — 모든 숫자가 계산 결과와 일치하는지 확인했습니다.")
        st.text(text)
        html = render_briefing(run, generated_at=pd.Timestamp.now(), data_as_of=q["as_of"])
        st.download_button("브리핑 HTML 저장", html, file_name=f"briefing_{emd}_{row['최대일']}.html", mime="text/html")

EXAMPLES = ["7월에 유동인구가 이상하게 많았던 곳 알려줘", "이호동 7월 28일에 사람이 왜 이렇게 많았어?",
            "버스 데이터는 어디서 가져온 거야?", "반출 가능한 결과물 기준이 뭐야?"]

with tab_ask:
    st.markdown("#### 질문하기 — 외부 LLM 없이 이 PC 안에서 답합니다")
    st.caption("질문 분류는 로컬 판단 모델(tev1), 지역·날짜 추출과 계산은 규칙·도구, 답변 숫자는 모두 계산 결과와 대조해 통과한 것만 보여 줍니다.")
    cols = st.columns(len(EXAMPLES))
    for c, ex in zip(cols, EXAMPLES):
        if c.button(ex, use_container_width=True):
            st.session_state["ask_q"] = ex
    with st.form("ask"):
        q_text = st.text_input("질문", key="ask_q", placeholder="예: 성산읍 1월 버스 이용이 왜 줄었어?")
        sent = st.form_submit_button("질문 보내기", type="primary")
    if sent and q_text.strip():
        with st.spinner("도구 실행·검증 중…"):
            st.session_state.setdefault("ask_hist", []).insert(0, answer(q_text.strip(), get_toolbox(), method=method, threshold=threshold))
    for i, run in enumerate(st.session_state.get("ask_hist", [])[:5]):
        with st.container(border=True):
            s = run.slots
            when = str(s.date.date()) if s.date is not None else (f"{s.start.date()}~{s.end.date()}" if s.start is not None else "전체 기간")
            st.markdown(f"**Q. {run.question}**")
            st.caption(f"질문 분류: {INTENT_KO[run.intent]} ({run.router}{f' {run.intent_prob:.0%}' if run.router != 'rule' else ''}) · "
                       f"읍면동: {s.emd or '-'} · 신호: {s.signal} · 날짜/기간: {when}")
            st.markdown(("✅ 검증 통과" if run.verified else "⚠️ 검증 미통과(답변 보류)"))
            st.markdown(run.final_text.replace("\n", "  \n"))
            if run.results:
                with st.expander(f"근거: 도구 호출 {len(run.results)}건과 결과", expanded=False):
                    for rid, r in run.results.items():
                        st.markdown(f"**[{rid}] {r.tool}** · 출처: {', '.join(r.sources) or '-'}")
                        st.json(r.data, expanded=False)
            if run.verify_errors:
                st.caption("검증 메시지: " + " / ".join(run.verify_errors[:3]))

with tab_quality:
    st.markdown("#### 데이터 기준일")
    st.table(pd.DataFrame(q["as_of"].items(), columns=["신호", "마지막 날짜"]))
    st.markdown("#### 위치 매핑")
    st.table(pd.DataFrame([{"대상": "버스 정류소", **q["bus_stations"]}, {"대상": "와이파이 AP그룹", **q["wifi_ap_groups"]}])
             .rename(columns={"mapped": "매핑", "unmatched": "매칭 실패"}))
    st.caption("수집이 끝나지 않은 신호는 끝까지 받은 기간만 표시합니다. 원인 판정은 상관에 기반한 후보이며 인과가 아닙니다.")
