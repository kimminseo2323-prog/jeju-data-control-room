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
from app.report.briefing import ResultStore, render_briefing, template_text
from app.store.cache import CacheStore
from app.store.jeju_map import CHUJA_LAT, emd_shapes, load_emd

st.set_page_config(page_title="제주 데이터 관제실", page_icon="📡", layout="wide")
UP, DOWN, PICK, INK = style.UP, style.DOWN, style.PICK, style.INK
STRONG = 6.0   # 지도에서 진하게 칠하는 점수(이 미만은 옅게)


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
def get_emd():
    return load_emd()


def short(emd: str) -> str:
    return emd.split(" ", 1)[-1]


def chuja_shift() -> tuple[float, float] | None:
    """추자면(본섬 북쪽 약 45km)을 본섬 서쪽 바다로 옮겨 그릴 거리. 지도 높이가 늘지 않게(세로가 늘면 섬이 작아진다) 옆에 둔다."""
    emd = get_emd()
    far = [e for e in emd["emd"] if e["label"][1] > CHUJA_LAT]
    main = [e["label"] for e in emd["emd"] if e["label"][1] <= CHUJA_LAT]
    if not far:
        return None
    lon0, lat0 = far[0]["label"]
    return (min(x for x, _ in main) - 0.17 - lon0, max(y for _, y in main) - 0.06 - lat0)


def draw_emd(fig, fills: dict[str, str], hover: dict[str, str], shift=None, include_chuja=True, edge: dict[str, str] | None = None) -> dict:
    """읍면동 경계를 칠한다. fills/hover/edge = {읍면동: 색·설명·테두리색}. 그린 모양을 돌려준다(라벨 위치용)."""
    shapes = emd_shapes(get_emd(), chuja_shift=shift, include_chuja=include_chuja)
    edge = edge or {}
    for name in sorted(shapes, key=lambda n: n in edge):   # 테두리 강조할 곳은 나중에(위에) 그린다
        sh = shapes[name]
        fig.add_scatter(x=sh["lon"], y=sh["lat"], mode="lines", fill="toself", fillcolor=fills.get(name, style.LAND),
                        line=dict(color=edge.get(name, "#FFFFFF"), width=1.6 if name in edge else 0.7),
                        hoveron="fills", hoverinfo="name", name=hover.get(name, name), showlegend=False)
    return shapes


# 동이 작게 몰려 있는 시내(제주시 북쪽 해안, 서귀포시 남쪽 해안): 이름을 바다 쪽으로 빼고 선으로 잇는다
CITY_ZONES = ((126.38, 126.72, 33.47, 90.0, 33.615), (126.45, 126.62, -90.0, 33.27, 33.155))   # 경도·위도 범위, 이름 줄의 위도


def label_ranked(fig, names: dict[str, str], shapes: dict) -> None:
    """지도에 이름 붙이기. 시내에 몰린 곳은 바다 위 한 줄에 경도 순으로 벌려 놓고 선으로 잇는다."""
    font = dict(size=12, color=INK, weight=600)
    rows: dict[int, list] = {}
    for e, text in names.items():
        if e not in shapes:
            continue
        x, y = shapes[e]["label"]
        fig.add_scatter(x=[x], y=[y], mode="markers", marker=dict(color=INK, size=6), hoverinfo="skip")
        zone = next((k for k, (x0, x1, y0, y1, _) in enumerate(CITY_ZONES) if x0 <= x <= x1 and y0 <= y <= y1), None)
        if zone is None:
            fig.add_annotation(x=x, y=y, text=text, showarrow=False, yshift=11, font={**font, "shadow": "0 0 3px #fff, 0 0 3px #fff"})
        else:
            rows.setdefault(zone, []).append((x, y, text))
    for zone, pts in rows.items():
        pts.sort()
        gap = 0.13
        mid = sum(p[0] for p in pts) / len(pts)
        for k, (x, y, text) in enumerate(pts):
            fig.add_annotation(x=x, y=y, ax=mid + (k - (len(pts) - 1) / 2) * gap, ay=CITY_ZONES[zone][4], axref="x", ayref="y",
                               text=text, showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor=INK, standoff=3, font=font)


def map_layout(fig, height: int) -> None:
    style.plot(fig, height=height)
    fig.update_layout(margin=dict(l=0, r=0, t=4, b=0), showlegend=False, hoverlabel=dict(namelength=-1),
                      xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x", scaleratio=1.2), dragmode="pan")


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


def span_text(start, end, days: int) -> str:
    return str(start) if start == end else f"{start}~{end} ({days}일)"


def period_label(period: str) -> str:
    if period == "전체 기간":
        return "전체 기간"
    y, m = period.split("-")
    return f"{y}년 {int(m)}월"


# ---------------- sidebar ----------------
store = get_store()
with st.sidebar:
    st.markdown("#### 보기 설정")
    signals = store.signals()
    signal = st.selectbox("신호", signals, index=0)
    method = st.radio("평소 값(기대값) 계산", ["seasonal_z", "robust_resid"],
                      format_func=lambda m: {"seasonal_z": "앞뒤 4주 같은 요일의 중앙값", "robust_resid": "STL 분해(추세+요일 주기)"}[m])
    threshold = st.slider("민감도: 이 점수 이상을 이상으로 봄", 2.5, 6.0, 3.5, 0.5,
                          help="점수 = 기대값과의 차이가 평소 변동폭의 몇 배인지. 높일수록 큰 변화만 남습니다.")
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
    st.caption(f"원인 판정 모델: {model_status()[1]}. 보기 중에서 고르기만 하고 문장은 만들지 않습니다.")

q = store.quality()
z, episodes = scan(signal, method, threshold)

st.markdown(style.CSS, unsafe_allow_html=True)
_cols = pd.DatetimeIndex(z.columns) if not z.empty else None
st.markdown(style.header_html(signal, q["as_of"].get(signal, "-"),
                              f"{_cols.min():%Y-%m-%d}~{_cols.max():%Y-%m-%d}" if _cols is not None else "-", len(z)),
            unsafe_allow_html=True)

tab_board, tab_detail, tab_ask, tab_quality = st.tabs(["관제판", "상세 분석·브리핑", "질문하기", "데이터 품질"])


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
        pc1, pc2 = st.columns([1, 4], vertical_alignment="bottom")
        period = pc1.selectbox("기간", board.months(z) + ["전체 기간"], index=0, key="board_period")
        start, end = (cols.min(), cols.max()) if period == "전체 기간" else board.month_bounds(period)
        pe = board.period_episodes(episodes, start, end)
        counts = board.daily_alarm_counts(z, threshold, start, end)
        regs = board.region_summary(z, threshold, start, end)
        peak_day = f"{counts.idxmax():%Y-%m-%d}" if len(counts) and counts.max() > 0 else None
        pc2.markdown(style.summary_html(period_label(period), len(pe), int((pe["유형"] == "지속 변화").sum()) if not pe.empty else 0,
                                        int((regs["alarm_days"] > 0).sum()), len(regs), peak_day, int(counts.max()) if peak_day else 0),
                     unsafe_allow_html=True)
        if st.session_state.get("picked_msg"):
            st.success(f"{st.session_state.pop('picked_msg')} 구간을 골라 두었습니다. 위의 '상세 분석·브리핑' 탭을 눌러 보세요.")

        top = pe.head(5)
        left, right = st.columns([7, 5], gap="large")
        with left:
            st.markdown("#### 어디서 달라졌나")
            if get_emd() is None:
                st.caption("읍면동 경계 파일(data/geo/jeju_emd.json)이 없어 지도를 그리지 못했습니다. python -m app.store.jeju_map 으로 만들 수 있습니다.")
            else:
                fills, hover = {}, {}
                for e, r in regs.iterrows():
                    v, hit = r["peak_z"], r["alarm_days"] > 0
                    if hit:
                        fills[e] = (UP if v >= STRONG else style.UP_SOFT) if v > 0 else (DOWN if v <= -STRONG else style.DOWN_SOFT)
                    hover[e] = (f"{e}<br>이상일 {int(r['alarm_days'])}일, 가장 큰 점수 {v:+.1f}" if hit else f"{e}<br>이상 없음")
                shift = chuja_shift()
                fmap = go.Figure()
                shapes = draw_emd(fmap, fills, hover, shift=shift)
                if shift and "제주시 추자면" in shapes:   # 옮겨 그린 추자면임을 점선 상자로 표시
                    xs = [x for x in shapes["제주시 추자면"]["lon"] if x is not None]
                    ys = [y for y in shapes["제주시 추자면"]["lat"] if y is not None]
                    fmap.add_shape(type="rect", x0=min(xs) - 0.03, x1=max(xs) + 0.03, y0=min(ys) - 0.03, y1=max(ys) + 0.035,
                                   line=dict(color=style.SUBTLE, width=1, dash="dot"))
                    fmap.add_annotation(x=(min(xs) + max(xs)) / 2, y=max(ys) + 0.035, yanchor="bottom", showarrow=False,
                                        text="추자면<br>(실제는 북쪽 45km)", font=dict(size=11, color=style.MUTED))
                ranks: dict[str, list[str]] = {}
                for rank, (_, r) in enumerate(top.iterrows(), 1):
                    ranks.setdefault(r["읍면동"], []).append(str(rank))
                label_ranked(fmap, {e: f"{','.join(ranks[e])} {short(e)}" for e in ranks}, shapes)
                map_layout(fmap, 430)
                st.plotly_chart(fmap, width="stretch", config={"displayModeBar": False, "scrollZoom": True})
                st.markdown(style.key_html([(UP, f"많음(점수 {STRONG:.0f} 이상)"), (style.UP_SOFT, "많음"), (style.LAND, "이상 없음"),
                                            (style.DOWN_SOFT, "적음"), (DOWN, f"적음(점수 {STRONG:.0f} 이상)")]), unsafe_allow_html=True)
                st.caption("읍면동마다 이 기간 가장 큰 변화의 방향과 크기로 칠했습니다. 숫자는 오른쪽 TOP 5 순위입니다. "
                           "제주시 동 지역은 작으니 마우스 휠로 확대해 보세요.")
        with right:
            st.markdown("#### 주요 이상 TOP 5")
            if top.empty:
                st.caption("이 기간에는 기준을 넘는 이상 구간이 없습니다.")
            qcs = [cached_quick_cause(signal, r["읍면동"], str(r["최대일"]), "up" if r["방향"] == "증가" else "down") for _, r in top.iterrows()]
            same_na = len({qc["unchecked"] for qc in qcs}) == 1 and qcs and qcs[0]["unchecked"]
            if same_na:   # 다섯 줄 모두 같은 '확인 불가'면 줄마다 반복하지 않고 위에 한 번만
                st.caption(f"이 기간은 {qcs[0]['unchecked'].replace(' 확인 불가', '')} 자료 제공 기간 밖이라 그 맥락은 확인하지 못했습니다.")
            for rank, ((i, r), qc) in enumerate(zip(top.iterrows(), qcs), 1):
                up = r["방향"] == "증가"
                st.markdown(style.episode_row_html(rank, r["읍면동"], span_text(r["시작"], r["끝"], r["일수"]), r["유형"], up,
                                                   r["기대 대비(%)"], r["점수"], qc["cause"], qc["points"], "" if same_na else qc["unchecked"]),
                            unsafe_allow_html=True)
                st.button("상세 분석 보기", key=f"go_{i}", type="tertiary", on_click=_pick_episode,
                          args=(int(i), f"{r['읍면동']} {r['최대일']}"))
            st.caption("원인 후보는 화면을 빨리 띄우려고 규칙으로 정한 '빠른 판정'입니다. 판단 모델의 판정과 검증된 브리핑은 상세 분석에서 봅니다.")

        st.markdown("#### 언제 달라졌나")
        isl = store.island_series(signal)
        isl = isl[(isl.index >= start) & (isl.index <= end)]
        ftr = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12, row_heights=[0.5, 0.5],
                            subplot_titles=(f"제주 전체 {signal}(하루 합계, 만)", "평소와 크게 달랐던 읍면동 수"))
        ftr.add_scatter(x=isl.index, y=isl.values / 1e4, line=dict(color=INK, width=1.6), name=f"제주 전체 {signal}",
                        hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.1f}만<extra></extra>", row=1, col=1)
        bar_col = [INK if (peak_day and f"{d:%Y-%m-%d}" == peak_day) else style.SUBTLE for d in counts.index]
        ftr.add_bar(x=counts.index, y=counts.values, marker_color=bar_col, marker_line_width=0, name="이상 읍면동 수",
                    hovertemplate="%{x|%Y-%m-%d}<br>%{y}곳<extra></extra>", row=2, col=1)
        if peak_day:
            ftr.add_annotation(x=counts.idxmax(), y=counts.max(), text=f"{counts.idxmax():%m-%d} {int(counts.max())}곳", showarrow=False,
                               yshift=10, font=dict(size=12, color=INK), row=2, col=1)
        style.plot(ftr, height=420)
        ftr.update_layout(margin=dict(l=0, r=0, t=28, b=0), showlegend=False, bargap=0.2, hovermode="x")
        ftr.update_annotations(selector=dict(text=f"제주 전체 {signal}(하루 합계, 만)"), x=0, xanchor="left", font=dict(size=13, color=style.INK_2))
        ftr.update_annotations(selector=dict(text="평소와 크게 달랐던 읍면동 수"), x=0, xanchor="left", font=dict(size=13, color=style.INK_2))
        ftr.update_yaxes(rangemode="tozero", row=2, col=1)
        ftr.update_xaxes(tickformat="%m-%d" if period != "전체 기간" else "%Y-%m")
        st.plotly_chart(ftr, width="stretch", config={"displayModeBar": False})
        st.caption("여러 곳이 같은 날 함께 달라졌다면 연휴·성수기·날씨처럼 섬 전체에 걸친 요인일 가능성이 큽니다.")

        with st.expander("읍면동 × 날짜 점수표(기준을 넘은 칸만 색칠)"):
            w = z.loc[:, (cols >= start) & (cols <= end)]
            wm = w.where(w.abs() >= threshold).clip(-8, 8)
            fig = px.imshow(wm, aspect="auto", color_continuous_scale=[[0, DOWN], [0.5, "#F4F4F4"], [1, UP]],
                            zmin=-8, zmax=8, labels={"color": "점수"})
            style.plot(fig, height=max(420, 16 * len(wm)))
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
            fig.update_xaxes(tickformat="%m-%d" if period != "전체 기간" else "%Y-%m")
            st.plotly_chart(fig, width="stretch")
        with st.expander(f"이 기간 이상 구간 전체 목록({len(pe)}개)"):
            st.dataframe(pe, width="stretch", hide_index=True, height=360)

with tab_detail:
    if episodes.empty:
        st.info("선택할 이상 구간이 없습니다.")
    else:
        labels = [f"{r['읍면동']}, {r['최대일']}, {r['방향']} {abs(r['기대 대비(%)'])}% ({r['유형']})" for _, r in episodes.iterrows()]
        # 신호·방법·민감도마다 따로 기억한다(같은 키로 목록이 바뀌면 브라우저가 값을 글자로 돌려보내 오류가 났음, 2026-11-13)
        pick_key = f"detail_pick|{signal}|{method}|{threshold}"
        goto = st.session_state.pop("detail_goto", None)   # 관제판 '상세 분석 보기'에서 고른 구간
        if isinstance(goto, int) and 0 <= goto < len(labels):
            st.session_state[pick_key] = goto
        cur = st.session_state.get(pick_key)
        if cur is not None and not (isinstance(cur, int) and 0 <= cur < len(labels)):
            del st.session_state[pick_key]
        pick = st.selectbox("이상 구간(점수 큰 순)", range(len(labels)), format_func=lambda i: labels[i], key=pick_key)
        row = episodes.iloc[pick]
        emd, day = row["읍면동"], pd.Timestamp(row["최대일"])
        up = row["방향"] == "증가"
        st.markdown(style.title_html(emd, signal, span_text(row["시작"], row["끝"], row["일수"]), up,
                                     f"가장 큰 날 {row['최대일']}: 기대값보다 {row['기대 대비(%)']:+.1f}%, 점수 {abs(row['점수']):.1f}, {row['유형']}"),
                    unsafe_allow_html=True)

        s = store.series(signal, emd)
        _, expected, zz = score_series(s, method)
        rng = st.segmented_control("그래프 범위", ["구간 앞뒤 8주", "전체 기간"], default="구간 앞뒤 8주", key="detail_range",
                                   label_visibility="collapsed") or "구간 앞뒤 8주"
        x0, x1 = (pd.Timestamp(row["시작"]) - pd.Timedelta(weeks=8), pd.Timestamp(row["끝"]) + pd.Timedelta(weeks=8)) \
            if rng == "구간 앞뒤 8주" else (s.index.min(), s.index.max())
        sw, ew, zw = s[x0:x1], expected[x0:x1], zz[x0:x1]
        fig = go.Figure()
        fig.add_vrect(x0=pd.Timestamp(row["시작"]) - pd.Timedelta(hours=12), x1=pd.Timestamp(row["끝"]) + pd.Timedelta(hours=12),
                      fillcolor=PICK, opacity=0.14, line_width=0)
        fig.add_scatter(x=ew.index, y=ew.values, name="기대값(평소)", line=dict(color=style.SUBTLE, width=1.5),
                        hovertemplate="기대값 %{y:,.0f}<extra></extra>")
        fig.add_scatter(x=sw.index, y=sw.values, name="실제", line=dict(color=INK, width=1.6), hovertemplate="실제 %{y:,.0f}<extra></extra>")
        an = zw[zw.abs() >= threshold].dropna()
        for name, part, col in (("평소보다 많은 날", an[an > 0], UP), ("평소보다 적은 날", an[an < 0], DOWN)):
            if len(part):
                fig.add_scatter(x=part.index, y=sw.reindex(part.index), mode="markers", name=name, hoverinfo="skip",
                                marker=dict(color=col, size=9, line=dict(color="#FFFFFF", width=2)))
        if day in sw.index:
            fig.add_annotation(x=day, y=sw[day], text=f"{row['기대 대비(%)']:+.0f}%", showarrow=False, yshift=14,
                               font=dict(size=12, color=UP if up else DOWN))
        style.plot(fig, height=340)
        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", legend=dict(y=1.12))
        fig.update_xaxes(hoverformat="%Y-%m-%d", tickformat="%m-%d" if rng == "구간 앞뒤 8주" else "%Y-%m")
        fig.update_yaxes(tickformat=",")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        tb = get_toolbox()
        res = {}
        for i, (name, args) in enumerate([
            ("detect_anomalies", {"signal": signal, "emd": emd, "method": method, "threshold": threshold,
                                  "start": str((day - pd.Timedelta(days=14)).date()), "end": str((day + pd.Timedelta(days=14)).date())}),
            ("find_co_movements", {"date": str(day.date()), "emd": emd, "window": 1, "exclude_signal": signal}),
            ("check_context", {"date": str(day.date()), "emd": emd, "signal": signal}),
        ], 1):
            res[f"R{i}"] = tb.dispatch(name, args, f"R{i}")

        items = res["R3"].data["items"]
        not_covered = res["R3"].data.get("not_covered", [])
        co = res["R2"].data["co_movements"]
        checked, no_data = res["R2"].data["checked"], res["R2"].data.get("no_data", [])

        left, right = st.columns([1, 1], gap="large")
        with left:
            st.markdown("#### 같은 날 맥락")
            rows = [("ok", it["detail"]) for it in items]
            if not items:   # 자료 기간 안에서 확인한 것만 '기록 없음'이라 말한다
                checked_kinds = [n for k, n in (("weather", "기상"), (None, "공휴일"), ("event", "행사"), ("visitors", "성수기·비수기"))
                                 if k not in not_covered]
                rows.append(("none", f"{'·'.join(checked_kinds)} 기록 없음"))
            if not_covered:
                rows.append(("na", f"{'·'.join(NOT_COVERED_KO.get(k, k) for k in not_covered)}: 이 날짜는 자료 제공 기간 밖"))
            st.markdown(style.evidence_html(rows), unsafe_allow_html=True)

            st.markdown("#### 함께 움직인 신호")
            rows = [("ok", f"{c['signal']}: {c['date']} 점수 {c['z']}") for c in co]
            if not co:
                rows.append(("none", f"확인한 신호({', '.join(checked)})는 함께 움직이지 않음") if checked else ("na", "이 날짜에 비교할 수 있는 다른 신호 자료 없음"))
            if no_data:
                rows.append(("na", f"자료 없음: {', '.join(no_data)}"))
            st.markdown(style.evidence_html(rows), unsafe_allow_html=True)
            st.caption("다른 신호 = 같은 읍면동의 버스·와이파이 등, 제주 전체 합계, 인근 읍면동(대표 좌표가 15km 안인 3곳).")
            if signal == "외국인":
                st.markdown("#### 국적별 변화(평소 대비)")
                try:
                    nm = tb.dispatch("nationality_mix", {"date": str(day.date()), "emd": emd, "top": 5}, "R4")
                    res["R4"] = nm
                    nat = pd.DataFrame(nm.data["top"]).rename(columns={
                        "nationality": "국적", "value": "그날", "expected": "기대값", "diff": "차이", "share_of_change": "전체 변화 중(%)"})
                    st.markdown(style.table_html(nat, num_cols=("그날", "기대값", "차이", "전체 변화 중(%)")), unsafe_allow_html=True)
                    if nm.data.get("no_baseline") or nm.data.get("no_value"):
                        st.caption("비교에서 뺀 국적(0명으로 치지 않음). 평소 기록 부족: " + (", ".join(nm.data.get("no_baseline", [])) or "없음")
                                   + ". 그날 값 없음: " + (", ".join(nm.data.get("no_value", [])) or "없음") + ".")
                except Exception as e:   # 국적 자료가 없는 날
                    st.caption(f"국적별 자료 없음: {e}")

        with right:
            st.markdown("#### 원인 후보 판정")
            evidence = {"anomaly": {"emd": emd, "signal": signal, "date": str(day.date()), "pct": float(row["기대 대비(%)"]),
                                    "kind": row["유형"], "days": int(row["일수"])},
                        "context": items, "co_movements": co, "not_covered": not_covered,
                        "co_checked": checked, "co_no_data": no_data}
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
                    rest = pr[pr["확률"] < 0.01]
                    pr = pr[pr["확률"] >= 0.01]   # 1% 미만 보기는 막대 대신 아래 한 줄로
                    bars = go.Figure(go.Bar(x=pr["확률"], y=pr["원인"], orientation="h", text=[f"{p:.0%}" for p in pr["확률"]],
                                            textposition="outside", cliponaxis=False, hoverinfo="skip",
                                            marker_color=[PICK if c == CAUSE_KO[j.choice] else style.LINE_STRONG for c in pr["원인"]]))
                    style.plot(bars, height=20 + 30 * len(pr))
                    bars.update_layout(margin=dict(l=0, r=40, t=0, b=0), bargap=0.55)
                    bars.update_xaxes(visible=False, range=[0, 1.08]).update_yaxes(title=None, gridcolor="#FFFFFF", ticks="")
                    st.plotly_chart(bars, width="stretch", config={"displayModeBar": False, "staticPlot": True})
                    if len(rest):
                        st.caption(f"1% 미만: {', '.join(rest['원인'][::-1])}")
            else:
                st.caption("판단 모델은 아래 근거만 보고 원인 보기 중 하나를 고릅니다.")
            with st.expander("판정 모델에 넘기는 근거"):
                st.text(evidence_text(evidence))

            cent = store.centroids
            if get_emd() is not None and emd in cent.index:
                st.markdown("#### 위치와 인근 읍면동")
                nb = [e for e in res["R2"].data.get("neighbors", []) if e in cent.index]
                is_chuja = cent.loc[emd, "lat"] > CHUJA_LAT
                fills = {emd: PICK, **{e: style.LINE_STRONG for e in nb}}
                hover = {emd: f"{emd}(고른 곳)", **{e: f"{e}(인근)" for e in nb}}
                loc = go.Figure()
                shapes = draw_emd(loc, fills, hover, include_chuja=is_chuja, edge={e: INK for e in nb})
                pts = [(e, shapes[e]["label"]) for e in [emd, *nb] if e in shapes]
                loc.add_scatter(x=[p[0] for _, p in pts], y=[p[1] for _, p in pts], mode="markers+text",
                                marker=dict(color=INK, size=[8] + [6] * (len(pts) - 1),
                                            line=dict(color="#FFFFFF", width=1.5)),
                                text=[short(e) for e, _ in pts], hoverinfo="skip",
                                textposition=["top center"] + [("middle left" if p[0] < pts[0][1][0] else "middle right") for _, p in pts[1:]],
                                textfont=dict(size=[13] + [11] * (len(pts) - 1), color=INK, shadow="0 0 3px #fff, 0 0 3px #fff"))
                map_layout(loc, 320)
                # 고른 곳과 이웃이 보이게 확대(동 지역은 작아서 섬 전체로 그리면 겹친다). 끌거나 휠로 넓혀 볼 수 있다
                xs = [x for e in [emd, *nb] if e in shapes for x in shapes[e]["lon"] if x is not None]
                ys = [y for e in [emd, *nb] if e in shapes for y in shapes[e]["lat"] if y is not None]
                cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
                half = max(max(xs) - min(xs), (max(ys) - min(ys)) * 1.2, 0.12) * 0.75
                loc.update_layout(xaxis=dict(range=[cx - half * 1.6, cx + half * 1.6]), yaxis=dict(range=[cy - half / 1.2, cy + half / 1.2]))
                st.plotly_chart(loc, width="stretch", config={"displayModeBar": False, "scrollZoom": True})
                st.markdown(style.key_html([(PICK, "고른 읍면동"), (style.LINE_STRONG, "인근 읍면동(함께 움직였는지 비교한 곳)")]),
                            unsafe_allow_html=True)
                st.caption("고른 곳 주변을 확대했습니다(마우스 휠로 넓혀 보기). "
                           + ("15km 안에 이웃 읍면동이 없어 인근 비교는 하지 않습니다." if not nb else ""))

        st.markdown("#### 브리핑")
        text = template_text(res)
        v = verify(text, res)
        if not v.ok:   # 질문하기와 같이, 검증을 통과하지 못한 문장은 보이지 않는다
            text = WITHHELD
        run = AgentRun(f"{emd} {signal} {row['최대일']} 이상 구간", [], results=res, final_text=text, verified=v.ok)
        st.markdown(style.check_html(v.ok, "문장의 모든 숫자가 계산 결과와 일치합니다." if v.ok else "문장은 표시하지 않습니다."),
                    unsafe_allow_html=True)
        st.markdown(style.answer_html(text), unsafe_allow_html=True)
        html = render_briefing(run, generated_at=pd.Timestamp.now(), data_as_of=q["as_of"])
        b1, b2, _ = st.columns([1, 1, 2])
        if b1.button("결과 폴더(data/results)에 저장", width="stretch"):
            st.session_state["saved_msg"] = get_results().save(f"briefing_{emd}_{row['최대일']}".replace(" ", "_"), html).name
            st.rerun()   # 사이드바의 삭제 버튼·개수를 바로 갱신
        b2.download_button("내 PC로 내려받기(HTML)", html, file_name=f"briefing_{emd}_{row['최대일']}.html", mime="text/html",
                           width="stretch")
        if st.session_state.get("saved_msg"):
            st.caption(f"저장함: {st.session_state['saved_msg']}")

EXAMPLES = ["7월에 유동인구가 이상하게 많았던 곳 알려줘", "이호동 2024년 7월 28일에 사람이 왜 이렇게 많았어?",
            "송산동 2024년 9월 29일에 외국인이 왜 많았어?", "반출 가능한 결과물 기준이 뭐야?"]


def _use_example() -> None:
    ex = st.session_state.get("ask_example")
    if ex:
        st.session_state["ask_q"] = ex


with tab_ask:
    st.markdown("#### 자료에 대해 물어보기")
    st.caption("읍면동·날짜·신호를 넣어 물어보세요. 답의 숫자는 모두 계산 결과와 대조해, 맞는 것만 보여 줍니다.")
    st.pills("예시 질문", EXAMPLES, key="ask_example", on_change=_use_example)
    with st.form("ask"):
        q_text = st.text_input("질문", key="ask_q", placeholder="예: 성산읍 1월 버스 이용이 왜 줄었어?")
        sent = st.form_submit_button("질문 보내기", type="primary")
    with st.expander("어떻게 답하나요"):
        st.markdown("- 지역·날짜를 읽고 계산하는 일은 코드가 합니다.\n"
                    "- 로컬 판단 모델 tev1은 질문 종류와 원인 후보를 보기 중에서 고르기만 하고, 고른 확률을 함께 보여 줍니다.\n"
                    "- 답변 문장은 계산 결과를 정해진 틀에 넣어 만듭니다. 글을 지어내는 생성형 AI는 쓰지 않습니다.\n"
                    "- 문장 끝의 작은 번호(R1, R2…)는 그 숫자를 낸 도구 결과입니다. '근거'를 열면 볼 수 있습니다.")
    if sent and q_text.strip():
        with st.spinner("도구 실행·검증 중…"):
            st.session_state.setdefault("ask_hist", []).insert(0, answer(q_text.strip(), get_toolbox(), method=method, threshold=threshold))
    for i, run in enumerate(st.session_state.get("ask_hist", [])[:5]):
        with st.container(border=True):
            s = run.slots
            when = str(s.date.date()) if s.date is not None else (f"{s.start.date()}~{s.end.date()}" if s.start is not None else "전체 기간")
            st.markdown(f"**{run.question}**")
            router = run.router + (f" {run.intent_prob:.0%}" if run.intent_prob > 0 else "")
            st.markdown(style.meta_html([("질문 종류", f"{INTENT_KO[run.intent]}({router})"), ("읍면동", s.emd or "-"),
                                         ("신호", s.signal), ("날짜", when)]), unsafe_allow_html=True)
            st.markdown(style.check_html(run.verified, "답의 숫자가 계산 결과와 일치합니다." if run.verified else "답변을 보류했습니다."),
                        unsafe_allow_html=True)
            st.markdown(style.answer_html(run.final_text), unsafe_allow_html=True)
            if run.results:
                with st.expander(f"근거: 도구 호출 {len(run.results)}건과 결과", expanded=False):
                    for rid, r in run.results.items():
                        st.markdown(f"**{rid}. {r.tool}** (출처: {', '.join(r.sources) or '-'})")
                        st.json(r.data, expanded=False)
            if run.verify_errors:
                st.caption("검증 메시지: " + " / ".join(run.verify_errors[:3]))

with tab_quality:
    st.markdown("#### 신호별 마지막 자료 날짜")
    st.markdown(style.table_html(pd.DataFrame(q["as_of"].items(), columns=["신호", "마지막 날짜"])), unsafe_allow_html=True)
    st.markdown("#### 위치 매핑(좌표 → 읍면동)")
    loc_df = pd.DataFrame([{"대상": "버스 정류소", **q["bus_stations"]}, {"대상": "와이파이 AP그룹", **q["wifi_ap_groups"]}]) \
        .rename(columns={"mapped": "매핑", "unmatched": "매칭 실패"})
    st.markdown(style.table_html(loc_df, num_cols=tuple(c for c in loc_df.columns if c != "대상")), unsafe_allow_html=True)
    if q.get("bus_usage"):
        st.markdown("#### 버스 이용 자료 → 읍면동 연결(이용자 수 기준)")
        bu = q["bus_usage"]
        bu_df = pd.DataFrame([{"연결 방법": k, "비율": f"{v:.1f}%"} for k, v in {
            "정류소ID 일치": bu["by_id"], "정류소 이름 일치": bu["by_name"],
            "같은 이름이 여러 읍면동(제외)": bu["ambiguous_name"], "매칭 실패(제외)": bu["unmatched"]}.items()])
        st.markdown(style.table_html(bu_df, num_cols=("비율",)), unsafe_allow_html=True)
        st.caption("이용 자료(613)와 정류소 정보(612)의 정류소ID 체계가 달라, 기호를 뺀 정류소 이름이 한 읍면동에만 있을 때 연결합니다. "
                   "여러 읍면동에 같은 이름이 있는 정류소(터미널 등)는 추측하지 않고 제외합니다.")
    emd_src = (get_emd() or {}).get("source")
    if emd_src:
        st.markdown("#### 지도 경계")
        st.caption(emd_src + ". 읍면동 이름 43곳이 분석 자료와 모두 일치합니다.")
    st.caption("수집이 끝나지 않은 신호는 끝까지 받은 기간만 표시합니다. 원인 판정은 상관에 기반한 후보이며 인과가 아닙니다.")
