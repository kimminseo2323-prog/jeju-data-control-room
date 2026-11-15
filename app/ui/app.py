"""제주 데이터 관제실 — 화면. 실행: streamlit run app/ui/app.py"""
from __future__ import annotations

import atexit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from app.agent.local import INTENT_KO, answer
from app.agent.loop import WITHHELD, AgentRun
from app.agent.tools import Toolbox
from app.agent.verify import verify
from app.analytics.detect import group_episodes, score_series, detect_anomalies
from app.llm.judge import CAUSE_KO, NOT_COVERED_KO, evidence_text, judge_cause, judgment_label, model_status
from app.rag.corpus import load_corpus
from app.rag.index import build_index
from app.report import board
from app.ui import style
from app.report.briefing import ResultStore, markdown_safe, render_briefing, template_text
from app.store.cache import CacheStore
from app.store.jeju_map import CHUJA_LAT, load_outline, outline_traces

st.set_page_config(page_title="제주 데이터 관제실", page_icon="📡", layout="wide")
UP, DOWN, PICK, INK = style.UP, style.DOWN, style.PICK, style.INK


@st.cache_resource
def get_store() -> CacheStore:
    return CacheStore(ROOT / "data" / "cache")


@st.cache_resource
def get_index():
    return build_index(load_corpus(ROOT))


@st.cache_resource
def get_results() -> ResultStore:
    """브리핑 저장 폴더(data/results). 화면 서버를 끌 때(Ctrl+C) '종료 시 삭제'가 켜져 있으면 이번 실행에서 저장한 파일을 지운다."""
    rs = ResultStore(ROOT / "data" / "results", delete_on_exit=True)
    atexit.register(rs.cleanup)
    return rs


@st.cache_resource
def get_toolbox() -> Toolbox:
    return Toolbox(get_store(), get_index())


@st.cache_resource
def get_outline():
    return load_outline()


def jeju_base(fig, chuja_shift=None, include_chuja=True) -> None:
    """제주 해안선·두 시 경계(연회색 면)를 지도 맨 아래에 깐다. 윤곽 파일(data/geo/jeju_outline.json)이 없으면 그리지 않는다."""
    outline = get_outline()
    if not outline:
        return
    for tr in outline_traces(outline, chuja_shift=chuja_shift, include_chuja=include_chuja):
        fig.add_scatter(x=tr["lon"], y=tr["lat"], mode="lines", fill="toself", fillcolor=style.LEDGER,
                        line=dict(color=style.LINE_STRONG, width=0.8), hoverinfo="skip", showlegend=False, name=tr["name"])


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
    return model_status()[1]


# ---------------- sidebar ----------------
store = get_store()
with st.sidebar:
    st.markdown("#### 보기 설정")
    signals = store.signals()
    signal = st.selectbox("신호", signals, index=0)
    method = st.radio("탐지 방법", ["seasonal_z", "robust_resid"],
                      format_func=lambda m: {"seasonal_z": "같은 요일 중앙값 기준", "robust_resid": "STL 분해 잔차"}[m])
    threshold = st.slider("민감도(점수 기준, 높을수록 엄격)", 2.5, 6.0, 3.5, 0.5)
    results_store = get_results()
    results_store.delete_on_exit = st.toggle("화면 종료 시 저장한 브리핑 삭제", value=True,
                                              help="센터 퇴실 시 삭제 원칙에 맞춘 기본값. 결과 폴더(data/results)에 저장한 파일만 해당합니다.")
    n_saved = sum(p.exists() for p in results_store.saved)
    if n_saved and st.button(f"저장한 브리핑 {n_saved}개 지금 삭제"):
        st.session_state["purged"] = results_store.purge()
        st.session_state.pop("saved_msg", None)
        st.rerun()
    if st.session_state.get("purged"):
        st.caption(f"저장한 브리핑 {st.session_state.pop('purged')}개를 삭제했습니다.")
    st.caption(f"판단 모델(보기 고르기 전용, 문장 생성 안 함): {judge_status()}")

q = store.quality()
z, episodes = scan(signal, method, threshold)

st.markdown(style.CSS, unsafe_allow_html=True)
_cols = pd.DatetimeIndex(z.columns) if not z.empty else None
st.markdown(style.header_html(signal, q["as_of"].get(signal, "-"),
                              f"{_cols.min():%Y-%m} ~ {_cols.max():%Y-%m}" if _cols is not None else "-", len(z)),
            unsafe_allow_html=True)

TABS = {"board": ":material/radar: 관제판", "detail": ":material/query_stats: 상세 분석·브리핑",
        "ask": ":material/forum: 질문하기", "quality": ":material/fact_check: 데이터 품질"}
tab_board, tab_detail, tab_ask, tab_quality = st.tabs(list(TABS.values()))

@st.cache_data(show_spinner=False)
def cached_quick_cause(signal: str, emd: str, day: str, direction: str) -> dict:
    return board.quick_cause(get_toolbox(), signal, emd, day, direction)


def _pick_episode(i: int, label: str) -> None:
    st.session_state["detail_goto"] = i
    st.session_state["picked_msg"] = label


with tab_board:
    if z.empty:
        st.info("이 신호는 아직 분석할 만큼 수집되지 않았습니다.")
    else:
        cols = pd.DatetimeIndex(z.columns)
        pc1, pc2 = st.columns([1, 3])
        period = pc1.selectbox("기간", board.months(z) + ["전체 기간"], index=0, key="board_period")
        start, end = (cols.min(), cols.max()) if period == "전체 기간" else board.month_bounds(period)
        pc2.caption("기간을 고르면 그 기간에 무엇이(주요 이상 TOP 5), 어디서(지도), 언제(날짜별 이상 읍면동 수) 달라졌는지 보여 줍니다.")
        pe = board.period_episodes(episodes, start, end)
        counts = board.daily_alarm_counts(z, threshold, start, end)
        regs = board.region_summary(z, threshold, start, end)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("이 기간 이상 구간", f"{len(pe)}개")
        k2.metric("그중 지속 변화(3일 이상)", f"{int((pe['유형'] == '지속 변화').sum()) if not pe.empty else 0}개")
        k3.metric("이상이 난 읍면동", f"{int((regs['alarm_days'] > 0).sum())}곳 / {len(regs)}곳")
        k4.metric("이상 읍면동이 가장 많은 날", f"{counts.idxmax():%Y-%m-%d} ({int(counts.max())}곳)" if len(counts) and counts.max() > 0 else "-")
        if st.session_state.get("picked_msg"):
            st.success(f"'{st.session_state.pop('picked_msg')}' 구간을 상세 분석·브리핑 탭에 선택해 두었습니다. 위의 탭을 눌러 보세요.")

        st.markdown("#### 이 기간 주요 이상 TOP 5")
        st.caption("점수(평소 변동폭 대비 크기) 순. 원인 후보는 화면을 빨리 띄우려고 규칙으로 정한 '빠른 판정'입니다. "
                   "판정 모델(tev1)의 판정과 검증된 브리핑은 '상세 보기'를 눌러 상세 분석 탭에서 확인하세요.")
        if pe.empty:
            st.info("이 기간에는 기준을 넘는 이상 구간이 없습니다.")
        for rank, (i, r) in enumerate(pe.head(5).iterrows(), 1):
            up = r["방향"] == "증가"
            qc = cached_quick_cause(signal, r["읍면동"], str(r["최대일"]), "up" if up else "down")
            span = str(r["시작"]) if r["시작"] == r["끝"] else f"{r['시작']} ~ {r['끝']}"
            row_col, btn_col = st.columns([11, 1.4], vertical_alignment="center", gap="small")
            row_col.markdown(style.episode_row_html(rank, r["읍면동"], span, r["유형"], up, r["기대 대비(%)"], r["점수"],
                                                    qc["cause"], qc["reason"]), unsafe_allow_html=True)
            btn_col.button("상세 보기", key=f"go_{i}", on_click=_pick_episode, args=(int(i), f"{r['읍면동']} {r['최대일']}"),
                           width="stretch")

        left, right = st.columns([2, 3])
        with left:
            st.markdown("#### 어디서")
            m = regs.join(store.centroids, how="inner").copy()
            far = m["lat"] > CHUJA_LAT   # 추자면(본섬 북쪽 약 45km)은 본섬 북서쪽 위에 붙여 그린다(지도가 작아지지 않게)
            main = m[~far]
            shift = None
            if far.any():
                old = m.loc[far, ["lon", "lat"]].iloc[0]
                new_lon, new_lat = main["lon"].min() + 0.03, main["lat"].max() + 0.12
                shift = (new_lon - old["lon"], new_lat - old["lat"])   # 추자 해안선도 같은 만큼 옮긴다
                m.loc[far, "lat"], m.loc[far, "lon"] = new_lat, new_lon
            hit = m["alarm_days"] > 0
            color = [(UP if v > 0 else DOWN) if h else style.LINE_STRONG for v, h in zip(m["peak_z"], hit)]
            size = [10 + 3 * min(abs(v), 10) if h else 7 for v, h in zip(m["peak_z"], hit)]
            top = set(m[hit]["peak_z"].abs().nlargest(8).index)
            fmap = go.Figure()
            jeju_base(fmap, chuja_shift=shift)
            if shift:   # 옮겨 그린 추자면임을 점선 상자로 표시
                fmap.add_shape(type="rect", x0=new_lon - 0.09, x1=new_lon + 0.09, y0=new_lat - 0.06, y1=new_lat + 0.07,
                               line=dict(color=style.SUBTLE, width=1, dash="dot"))
            fmap.add_trace(go.Scatter(
                x=m["lon"], y=m["lat"], mode="markers+text", marker=dict(color=color, size=size, opacity=0.9, line=dict(color="white", width=1)),
                text=[(e.split(" ")[1] + ("↑" if f else "")) if (e in top or f) else "" for e, f in zip(m.index, far)],
                textposition="top center", textfont=dict(size=11, color=INK),
                hovertext=[f"{e}<br>가장 큰 점수 {v:+.1f}, 이상일 {n}일" for e, v, n in zip(m.index, m["peak_z"], m["alarm_days"])],
                hoverinfo="text", showlegend=False))
            style.plot(fmap, height=380)
            fmap.update_layout(margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                               xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1.2))
            st.plotly_chart(fmap, width="stretch")
            st.markdown(style.key_html([(UP, "평소보다 많았던 곳"), (DOWN, "적었던 곳"), (style.LINE_STRONG, "이상 없음")]), unsafe_allow_html=True)
            st.caption("읍면동 위치는 정류소·AP 좌표 평균, 바탕은 제주시·서귀포시 경계입니다. 원이 클수록 변화가 크고, 이름은 변화가 큰 8곳만 붙였습니다"
                       "(나머지는 마우스를 올리면 보임). 점선 상자 안의 추자면↑은 실제로 본섬 북쪽 약 45km에 있습니다.")
        with right:
            st.markdown("#### 언제")
            isl = store.island_series(signal)
            isl = isl[(isl.index >= start) & (isl.index <= end)]
            ftr = make_subplots(specs=[[{"secondary_y": True}]])
            ftr.add_bar(x=counts.index, y=counts.values, name="이상 읍면동 수", marker_color=style.INK_2, marker_line_width=0)
            ftr.add_scatter(x=isl.index, y=isl.values, name=f"제주 전체 {signal}", line=dict(color=style.SUBTLE, width=1.5), secondary_y=True)
            style.plot(ftr, height=380)
            ftr.update_layout(margin=dict(l=0, r=0, t=10, b=0), bargap=0.15)
            ftr.update_yaxes(title_text="이상 읍면동 수", secondary_y=False, title_font_color=style.MUTED, tickfont_color=style.MUTED)
            ftr.update_yaxes(title_text=f"제주 전체 {signal}", secondary_y=True, showgrid=False, title_font_color=style.MUTED,
                             tickfont_color=style.MUTED)
            st.plotly_chart(ftr, width="stretch")
            st.caption("막대 = 그날 평소와 크게 달랐던 읍면동 수(여러 곳이 함께 움직인 날은 연휴·성수기처럼 섬 전체 요인일 가능성이 큼), 선 = 제주 전체 합계.")

        with st.expander("읍면동 × 날짜 점수 지도 (기준을 넘은 칸만 색칠)"):
            w = z.loc[:, (cols >= start) & (cols <= end)]
            wm = w.where(w.abs() >= threshold).clip(-8, 8)
            fig = px.imshow(wm, aspect="auto", color_continuous_scale=[[0, DOWN], [0.5, "#F4F4F4"], [1, UP]],
                            zmin=-8, zmax=8, labels={"color": "점수"})
            style.plot(fig, height=max(420, 16 * len(wm)))
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        with st.expander(f"이 기간 이상 구간 전체 목록 ({len(pe)}개)"):
            st.dataframe(pe, width="stretch", hide_index=True, height=360)

with tab_detail:
    if episodes.empty:
        st.info("선택할 이상 구간이 없습니다.")
    else:
        labels = [f"{r['읍면동']} · {r['최대일']} · {r['유형']} · {r['방향']} {abs(r['기대 대비(%)'])}%" for _, r in episodes.iterrows()]
        # 신호·방법·민감도마다 따로 기억한다(같은 키로 목록이 바뀌면 브라우저가 값을 글자로 돌려보내 오류가 났음, 2026-11-13)
        pick_key = f"detail_pick|{signal}|{method}|{threshold}"
        goto = st.session_state.pop("detail_goto", None)   # 관제판 '상세 보기'에서 고른 구간
        if isinstance(goto, int) and 0 <= goto < len(labels):
            st.session_state[pick_key] = goto
        cur = st.session_state.get(pick_key)
        if cur is not None and not (isinstance(cur, int) and 0 <= cur < len(labels)):
            del st.session_state[pick_key]
        pick = st.selectbox("이상 구간 선택", range(len(labels)), format_func=lambda i: labels[i], key=pick_key)
        row = episodes.iloc[pick]
        emd, day = row["읍면동"], pd.Timestamp(row["최대일"])

        s = store.series(signal, emd)
        _, expected, zz = score_series(s, method)
        fig = go.Figure()
        fig.add_scatter(x=s.index, y=s.values, name="실제", line=dict(color=INK, width=1.3))
        fig.add_scatter(x=expected.index, y=expected.values, name="기대값(기준선)", line=dict(color=style.SUBTLE, dash="dot", width=1.3))
        an = zz[zz.abs() >= threshold].dropna()
        for name, part, col in (("평소보다 많은 날", an[an > 0], UP), ("평소보다 적은 날", an[an < 0], DOWN)):
            fig.add_scatter(x=part.index, y=s.reindex(part.index), mode="markers", name=name, marker=dict(color=col, size=8, symbol="square"))
        fig.add_vrect(x0=pd.Timestamp(row["시작"]) - pd.Timedelta(hours=12), x1=pd.Timestamp(row["끝"]) + pd.Timedelta(hours=12),
                      fillcolor=PICK, opacity=0.18, line_width=0)
        style.plot(fig, height=320)
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

        tb = get_toolbox()
        res = {}
        for i, (name, args) in enumerate([
            ("detect_anomalies", {"signal": signal, "emd": emd, "method": method, "threshold": threshold,
                                  "start": str((day - pd.Timedelta(days=14)).date()), "end": str((day + pd.Timedelta(days=14)).date())}),
            ("find_co_movements", {"date": str(day.date()), "emd": emd, "window": 1, "exclude_signal": signal}),
            ("check_context", {"date": str(day.date()), "emd": emd, "signal": signal}),
        ], 1):
            res[f"R{i}"] = tb.dispatch(name, args, f"R{i}")

        left, right = st.columns([1, 1])
        with left:
            st.markdown("#### 같은 날 맥락")
            items = res["R3"].data["items"]
            not_covered = res["R3"].data.get("not_covered", [])
            lines = [f"- {it['detail']}" for it in items]
            if not items:   # 자료 기간 안에서 확인한 것만 '기록 없음'이라 말한다
                checked_kinds = [n for k, n in (("weather", "기상"), (None, "공휴일"), ("event", "행사"), ("visitors", "성수기·비수기"))
                                 if k not in not_covered]
                lines.append(f"- {'·'.join(checked_kinds)} 기록 없음")
            if not_covered:
                lines.append(f"- {'·'.join(NOT_COVERED_KO.get(k, k) for k in not_covered)}: 이 날짜는 자료 제공 기간 밖이라 확인하지 못함")
            st.write("\n".join(lines))
            st.markdown("#### 다른 신호·제주 전체·인근 읍면동 동반 변화")
            co = res["R2"].data["co_movements"]
            checked, no_data = res["R2"].data["checked"], res["R2"].data.get("no_data", [])
            co_lines = [f"- {c['signal']} {c['date']} 점수 {c['z']}" for c in co]
            if not co:
                co_lines.append(f"- 확인한 신호({', '.join(checked)}) 중 동반 변화 없음" if checked else "- 이 날짜에 비교할 수 있는 다른 신호 자료 없음")
            if no_data:
                co_lines.append(f"- 자료 없음(확인 불가): {', '.join(no_data)}")
            st.write("\n".join(co_lines))
            if signal == "외국인":
                st.markdown("#### 국적별 변화(평소 대비)")
                try:
                    nm = tb.dispatch("nationality_mix", {"date": str(day.date()), "emd": emd, "top": 5}, "R4")
                    res["R4"] = nm
                    st.dataframe(pd.DataFrame(nm.data["top"]).rename(columns={
                        "nationality": "국적", "value": "그날", "expected": "기대값", "diff": "차이", "share_of_change": "전체 변화 중(%)"}),
                        hide_index=True, width="stretch")
                    if nm.data.get("no_baseline") or nm.data.get("no_value"):
                        st.caption("비교에서 뺀 국적(0명으로 치지 않음) — 평소 기록 부족: " + (", ".join(nm.data.get("no_baseline", [])) or "-")
                                   + " / 그날 값 없음: " + (", ".join(nm.data.get("no_value", [])) or "-"))
                except Exception as e:   # 국적 자료가 없는 날
                    st.caption(f"국적별 자료 없음: {e}")
        with right:
            st.markdown("#### 원인 후보 판정")
            evidence = {"anomaly": {"emd": emd, "signal": signal, "date": str(day.date()), "pct": float(row["기대 대비(%)"]),
                                    "kind": row["유형"], "days": int(row["일수"])},
                        "context": items, "co_movements": co, "not_covered": not_covered,
                        "co_checked": res["R2"].data["checked"], "co_no_data": res["R2"].data.get("no_data", [])}
            with st.expander("판정 모델에 넘긴 근거(이 내용만 보고 판단)"):
                st.text(evidence_text(evidence))
            if st.button("원인 판정 실행", type="primary"):
                with st.spinner("판정 중…"):
                    st.session_state["judge"] = (labels[pick], judge_cause(evidence))
            if st.session_state.get("judge", (None,))[0] == labels[pick]:
                j = st.session_state["judge"][1]
                st.markdown(f"**{judgment_label(j)}**")
                if j.note:
                    st.caption(j.note)
                if j.backend != "rule":   # 규칙 판정의 보기 확률은 고정값이라 그리지 않는다
                    pr = pd.DataFrame({"원인": [CAUSE_KO[k] for k in j.probabilities], "확률": list(j.probabilities.values())}).sort_values("확률")
                    bars = px.bar(pr, x="확률", y="원인", orientation="h")
                    bars.update_traces(marker_color=[PICK if c == CAUSE_KO[j.choice] else style.LINE_STRONG for c in pr["원인"]])
                    bars.update_yaxes(title=None).update_xaxes(title=None, tickformat=".0%")
                    st.plotly_chart(style.plot(bars, height=240).update_layout(margin=dict(l=0, r=0, t=0, b=0)),
                                    width="stretch")

        with right:   # 위치: 고른 읍면동과 '인근 읍면동' 동반 변화에 쓴 이웃(제주 윤곽 위)
            cent = store.centroids
            if emd in cent.index:
                st.markdown("#### 위치와 인근 읍면동")
                nb = res["R2"].data.get("neighbors", [])
                is_chuja = cent.loc[emd, "lat"] > CHUJA_LAT
                pts = cent if is_chuja else cent[cent["lat"] <= CHUJA_LAT]
                loc = go.Figure()
                jeju_base(loc, include_chuja=is_chuja)
                others = pts.drop(index=[e for e in [emd, *nb] if e in pts.index])
                loc.add_scatter(x=others["lon"], y=others["lat"], mode="markers", marker=dict(color=style.LINE_STRONG, size=6),
                                hovertext=list(others.index), hoverinfo="text", showlegend=False)
                if nb:
                    loc.add_scatter(x=cent.loc[nb, "lon"], y=cent.loc[nb, "lat"], mode="markers+text", text=[e.split(" ")[1] for e in nb],
                                    textposition="bottom center", textfont=dict(size=11, color=style.INK_2),
                                    marker=dict(color="#FFFFFF", size=11, line=dict(color=INK, width=2)), name="인근 읍면동", hoverinfo="text",
                                    hovertext=nb)
                loc.add_scatter(x=[cent.loc[emd, "lon"]], y=[cent.loc[emd, "lat"]], mode="markers+text", text=[emd.split(" ")[1]],
                                textposition="top center", textfont=dict(size=12, color=INK), marker=dict(color=PICK, size=14),
                                name="고른 읍면동", hoverinfo="text", hovertext=[emd])
                style.plot(loc, height=280)
                loc.update_layout(margin=dict(l=0, r=0, t=6, b=0), showlegend=False,
                                  xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1.2))
                st.plotly_chart(loc, width="stretch")
                st.markdown(style.key_html([(PICK, "고른 읍면동"), (INK, "인근 읍면동(동반 변화 비교에 씀)")]), unsafe_allow_html=True)
                st.caption("인근 읍면동 = 대표 좌표가 가까운 3곳(15km 이내). " + ("이웃이 15km 안에 없어 인근 비교를 하지 않습니다." if not nb else ""))

        st.markdown("#### 브리핑")
        text = template_text(res)
        v = verify(text, res)
        if not v.ok:   # 질문하기와 같이, 검증을 통과하지 못한 문장은 보이지 않는다
            text = WITHHELD
        run = AgentRun(f"{emd} {signal} {row['최대일']} 이상 구간", [], results=res, final_text=text, verified=v.ok)
        st.markdown("✅ 검증 통과 — 문장의 모든 숫자가 계산 결과와 일치합니다." if v.ok else "⚠️ 검증 미통과 — 문장은 표시하지 않습니다.")
        st.text(text)
        html = render_briefing(run, generated_at=pd.Timestamp.now(), data_as_of=q["as_of"])
        b1, b2 = st.columns(2)
        if b1.button("결과 폴더(data/results)에 저장"):
            st.session_state["saved_msg"] = get_results().save(f"briefing_{emd}_{row['최대일']}".replace(" ", "_"), html).name
            st.rerun()   # 사이드바의 삭제 버튼·개수를 바로 갱신
        if st.session_state.get("saved_msg"):
            b1.success(f"저장: {st.session_state['saved_msg']}")
        b2.download_button("내 PC로 내려받기(HTML)", html, file_name=f"briefing_{emd}_{row['최대일']}.html", mime="text/html")

EXAMPLES = ["7월에 유동인구가 이상하게 많았던 곳 알려줘", "이호동 2024년 7월 28일에 사람이 왜 이렇게 많았어?",
            "송산동 2024년 9월 29일에 외국인이 왜 많았어?", "반출 가능한 결과물 기준이 뭐야?"]

with tab_ask:
    st.markdown("#### 질문하기")
    st.caption("답변 문장은 계산 결과를 정해진 틀에 넣어 만듭니다(글을 생성하는 AI는 쓰지 않습니다). "
               "로컬 판단 모델 tev1은 질문 종류와 원인 후보를 보기 중에서 고르기만 하고, 그 확률을 함께 보여 줍니다. "
               "지역·날짜 추출과 계산은 코드가 하고, 답변의 숫자는 계산 결과와 대조해 통과한 것만 보여 줍니다.")
    cols = st.columns(len(EXAMPLES))
    for c, ex in zip(cols, EXAMPLES):
        if c.button(ex, width="stretch"):
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
            st.caption(f"질문 분류: {INTENT_KO[run.intent]} ({run.router}{f' {run.intent_prob:.0%}' if run.intent_prob > 0 else ''}) · "
                       f"읍면동: {s.emd or '-'} · 신호: {s.signal} · 날짜/기간: {when}")
            st.markdown(("✅ 검증 통과" if run.verified else "⚠️ 검증 미통과(답변 보류)"))
            st.markdown(markdown_safe(run.final_text))
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
    if q.get("bus_usage"):
        st.markdown("#### 버스 이용 데이터 → 읍면동 연결 (이용자 수 기준 %)")
        bu = q["bus_usage"]
        st.table(pd.DataFrame([{k: f"{v:.1f}%" for k, v in {"정류소ID 일치": bu["by_id"], "정류소 이름 일치": bu["by_name"],
                                "같은 이름이 여러 읍면동(제외)": bu["ambiguous_name"], "매칭 실패(제외)": bu["unmatched"]}.items()}]))
        st.caption("이용 데이터(613)와 정류소 정보(612)의 정류소ID 체계가 달라, 기호를 뺀 정류소 이름이 한 읍면동에만 있을 때 연결합니다. "
                   "여러 읍면동에 같은 이름이 있는 정류소(터미널 등)는 추측하지 않고 제외합니다.")
    st.caption("수집이 끝나지 않은 신호는 끝까지 받은 기간만 표시합니다. 원인 판정은 상관에 기반한 후보이며 인과가 아닙니다.")
