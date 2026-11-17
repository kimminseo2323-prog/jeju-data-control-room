"""화면 스타일. 기준: docs/디자인_기준.md (IBM Carbon 구조 + 출발 안내판식 신호색).

- 구조: 각진 모서리, 1px 선, 흰색·연회색(#F4F4F4) 면 단계. 그림자·그라데이션·둥근 카드는 쓰지 않는다.
- 색은 뜻이 있을 때만: 빨강 = 평소보다 많음, 파랑 = 평소보다 적음, 귤색 = 지금 고른 것(탭·구간·판정). 나머지는 먹색과 회색.
- 힘을 주는 곳은 하나: 관제판의 읍면동 지도. 나머지는 조용하게.
- 숫자 카드 줄 대신 문장으로 요약하고, 근거는 '확인됨·기록 없음·확인 불가'를 구분해 줄마다 적는다(2026-11-15 가독성 개선).
- 글꼴은 app/ui/static/fonts 의 IBM Plex Sans KR(OFL)을 이 PC에서 내보낸다(외부 글꼴 서버를 부르지 않음).
"""
from __future__ import annotations

import html
import numbers
import re

INK, INK_2, MUTED, SUBTLE = "#161616", "#393939", "#525252", "#8D8D8D"
LEDGER, LINE, LINE_STRONG = "#F4F4F4", "#E0E0E0", "#C6C6C6"
UP, DOWN, PICK = "#DA1E28", "#0043CE", "#E8630A"   # 많음 · 적음 · 지금 고른 것(감귤색)
UP_SOFT, DOWN_SOFT = "#FF8389", "#78A9FF"           # 지도: 기준은 넘었지만 크지 않은 곳(점수 6 미만)
LAND = "#E8E8E8"                                    # 지도: 이상이 없었던 읍면동
FONT = "IBM Plex Sans KR, Malgun Gothic, sans-serif"

CSS = f"""
<style>
:root {{ --jj-ink:{INK}; --jj-ink2:{INK_2}; --jj-muted:{MUTED}; --jj-subtle:{SUBTLE}; --jj-ledger:{LEDGER};
        --jj-line:{LINE}; --jj-line-strong:{LINE_STRONG}; --jj-up:{UP}; --jj-down:{DOWN}; --jj-pick:{PICK}; }}
.block-container {{ padding-top:2.6rem; max-width:1500px; }}
p, li, label, .stMarkdown {{ letter-spacing:0.1px; }}
h4 {{ font-weight:600 !important; font-size:1.05rem !important; color:var(--jj-ink); padding:0 !important; margin:26px 0 8px !important; }}
[data-testid="stCaptionContainer"] {{ color:var(--jj-muted); }}
[data-testid="stHeaderActionElements"] {{ display:none; }}

/* 머리글: 화면 이름과 지금 보는 것을 한 문장으로 */
.jj-head {{ padding:0 0 14px; }}
.jj-head h1 {{ font-size:1.7rem !important; font-weight:600 !important; letter-spacing:-0.3px; margin:0 !important; padding:0 !important; color:var(--jj-ink); }}
.jj-head p {{ margin:4px 0 0; color:var(--jj-muted); font-size:0.98rem; }}
.jj-head p b {{ color:var(--jj-ink); font-weight:600; }}

/* 탭: 붙어 있는 큰 칸, 고른 칸은 흰 바탕에 위쪽 귤색 막대 */
.stTabs [role="tablist"] {{ gap:2px; border-bottom:none !important; box-shadow:none !important; flex-wrap:wrap; }}
.stTabs [role="tablist"]::before, .stTabs [role="tablist"]::after {{ display:none !important; }}
.stTabs [data-testid="stTab"] {{
    flex:1 1 160px; min-height:50px; padding:0 18px !important; justify-content:flex-start;
    background:{LEDGER}; color:{MUTED} !important; border:none; border-radius:0; border-top:3px solid transparent; border-bottom:1px solid {LINE_STRONG} !important;
    cursor:pointer; }}
.stTabs [data-testid="stTab"] p {{ font-size:1rem !important; font-weight:400 !important; }}
.stTabs [data-testid="stTab"]:hover {{ background:{LINE}; color:{INK} !important; }}
.stTabs [data-testid="stTab"][aria-selected="true"] {{ background:#FFFFFF; color:{INK} !important; border-top-color:var(--jj-pick);
    border-bottom-color:transparent !important; box-shadow:inset 1px 0 0 {LINE_STRONG}, inset -1px 0 0 {LINE_STRONG}; }}
.stTabs [data-testid="stTab"][aria-selected="true"] p {{ font-weight:600 !important; }}
.stTabs [data-testid="stTab"]::after, .stTabs [data-testid="stTab"]::before {{ display:none !important; }}
.stTabs [data-testid="stTab"]:focus-visible {{ outline:2px solid {INK}; outline-offset:-2px; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none !important; }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top:18px; }}

/* 기간 요약 문장 */
.jj-sum {{ font-size:1.12rem; line-height:1.6; color:var(--jj-ink2); margin:0; max-width:70em; }}
.jj-sum b {{ color:var(--jj-ink); font-weight:600; }}

/* TOP 5 카드: 컨테이너(st-key-ep_순위_방향)가 왼쪽 막대를 그려 '상세 분석 보기'까지 한 장으로 묶는다. 막대 색 = 방향 */
[class*="st-key-ep_"] {{ border-left:3px solid var(--jj-subtle); padding:10px 14px 10px 12px; gap:4px !important; background:#FFFFFF; }}
[class*="st-key-ep_"][class*="_up"] {{ border-left-color:var(--jj-up); }}
[class*="st-key-ep_"][class*="_down"] {{ border-left-color:var(--jj-down); }}
[class*="st-key-ep_"] [data-testid="stMarkdownContainer"] {{ margin-bottom:0 !important; }}   /* Streamlit 기본 -15px 때문에 버튼이 윗줄에 겹쳤음 */
[class*="st-key-ep_"] [data-testid="stButton"] {{ padding-left:42px; }}
.jj-row {{ display:grid; grid-template-columns:30px 1fr auto; column-gap:12px; }}
/* 좁은 칸에서 한글 낱말·날짜가 중간에서 끊기지 않게 */
.jj-row, .jj-sum, .jj-ev, .jj-answer, .jj-title {{ word-break:keep-all; overflow-wrap:anywhere; }}
.jj-row .nw {{ white-space:nowrap; }}
.jj-row .rank {{ font-size:1.25rem; font-weight:600; color:var(--jj-ink); line-height:1.3; }}
.jj-row .name {{ font-weight:600; font-size:1.02rem; color:var(--jj-ink); }}
.jj-row .when {{ color:var(--jj-muted); font-size:0.86rem; margin-top:1px; }}
.jj-row .pct {{ text-align:right; font-size:1.3rem; font-weight:400; line-height:1.3; white-space:nowrap; }}
.jj-row.up .pct {{ color:var(--jj-up); }} .jj-row.down .pct {{ color:var(--jj-down); }}
.jj-row .pct small {{ display:block; font-size:0.78rem; color:var(--jj-muted); }}
.jj-row .why {{ grid-column:2 / -1; margin-top:6px; font-size:0.9rem; color:var(--jj-ink2); line-height:1.55; }}
.jj-row .why b {{ font-weight:600; color:var(--jj-ink); margin-right:6px; }}
.jj-row .why .na {{ display:block; color:var(--jj-subtle); font-size:0.82rem; }}

/* 근거 목록(상세 탭): 줄마다 상태 표시 */
.jj-ev {{ border-top:1px solid var(--jj-line); }}
.jj-ev > div {{ display:grid; grid-template-columns:74px 1fr; gap:10px; padding:9px 0; border-bottom:1px solid var(--jj-line); font-size:0.95rem; line-height:1.5; }}
.jj-st {{ display:inline-block; font-size:0.76rem; padding:1px 6px; height:fit-content; text-align:center; border:1px solid; }}
.jj-st.ok {{ color:var(--jj-ink); border-color:var(--jj-ink); }}
.jj-st.none {{ color:var(--jj-muted); border-color:var(--jj-line-strong); }}
.jj-st.na {{ color:var(--jj-subtle); border-color:var(--jj-line-strong); border-style:dashed; }}

/* 상세 탭 제목 문장 */
.jj-title {{ font-size:1.3rem; font-weight:600; color:var(--jj-ink); margin:6px 0 2px; line-height:1.45; }}
.jj-title .up {{ color:var(--jj-up); }} .jj-title .down {{ color:var(--jj-down); }}
.jj-sub {{ color:var(--jj-muted); font-size:0.92rem; margin-bottom:4px; }}

/* 검증 결과 표시 */
.jj-check {{ border-left:3px solid var(--jj-ink); padding:6px 12px; margin:6px 0 10px; background:var(--jj-ledger); font-size:0.92rem; }}
.jj-check.fail {{ border-left-color:var(--jj-up); }}
.jj-check b {{ font-weight:600; margin-right:8px; }}

/* 답변 본문: 문장 끝 근거 번호는 작게 */
.jj-answer p {{ margin:0 0 6px; line-height:1.7; font-size:1rem; color:var(--jj-ink); }}
.jj-answer sup {{ color:var(--jj-subtle); font-size:0.7rem; margin-left:2px; }}
.jj-meta {{ display:flex; flex-wrap:wrap; gap:4px 18px; font-size:0.84rem; color:var(--jj-muted); margin:2px 0 8px; }}
.jj-meta b {{ color:var(--jj-ink2); font-weight:600; margin-right:4px; }}

/* 표 */
.jj-table {{ border-collapse:collapse; width:100%; font-size:0.93rem; margin:4px 0 8px; border:none !important; }}
.jj-table th, .jj-table td {{ border-left:none !important; border-right:none !important; border-top:none !important; }}
.jj-table th {{ text-align:left; font-weight:600; color:var(--jj-ink2); background:var(--jj-ledger); padding:8px 12px; border-bottom:1px solid var(--jj-line-strong); }}
.jj-table td {{ padding:8px 12px; border-bottom:1px solid var(--jj-line); }}
.jj-table .n {{ text-align:right; font-variant-numeric:tabular-nums; }}

/* 범례 */
.jj-key {{ display:inline-flex; align-items:center; vertical-align:middle; gap:6px; margin-right:16px; color:var(--jj-muted); font-size:0.84rem; }}
.jj-key i {{ width:12px; height:12px; display:inline-block; }}
.jj-key i.ln {{ width:18px; height:2px; }}
.jj-key i.dot {{ width:9px; height:9px; border-radius:50%; }}
.jj-key i.ring {{ background:#FFFFFF !important; border:2px solid {INK}; width:10px; height:10px; }}

/* 버튼: 기본은 먹색 테두리, 주요 동작은 먹색 채움, 줄 안의 '상세 보기'는 글자 버튼 */
[data-testid="stBaseButton-secondary"] {{ border:1px solid {INK} !important; color:{INK} !important; background:#FFFFFF !important; }}
[data-testid="stBaseButton-secondary"]:hover {{ background:{INK} !important; color:#FFFFFF !important; }}
[data-testid="stBaseButton-secondary"]:hover p {{ color:#FFFFFF !important; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{ background:{INK} !important; border-color:{INK} !important; }}
[data-testid="stBaseButton-tertiary"] {{ color:{DOWN} !important; padding:0 !important; min-height:0 !important; }}
[data-testid="stBaseButton-tertiary"] p {{ font-size:0.88rem !important; text-decoration:underline; text-underline-offset:3px; }}
[data-testid="stBaseButton-tertiary"]:hover p {{ color:{INK} !important; }}

[data-testid="stSidebar"] {{ border-right:1px solid var(--jj-line); }}
/* 위젯 이름표·본문도 낱말 중간에서 줄을 바꾸지 않는다(사이드바 '브리핑 삭/제'처럼 끊기던 문제, 11/17) */
[data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{ word-break:keep-all; overflow-wrap:anywhere; }}
[data-testid="stExpander"] details {{ border-radius:0; border-color:var(--jj-line); }}
</style>
"""


def _e(s) -> str:
    return html.escape(str(s))


def header_html(signal: str, as_of: str, period: str, n_emd: int) -> str:
    """머리글: 화면 이름 + 지금 무엇을 보는지 한 문장."""
    return (f'<div class="jj-head"><h1>제주 데이터 관제실</h1>'
            f'<p>읍면동 <b>{n_emd}곳</b>의 <b>{_e(signal)}</b>를 날마다 평소와 비교합니다. '
            f'자료 기간 {_e(period)}, 마지막 자료 <b>{_e(as_of)}</b>.</p></div>')


def summary_html(period: str, n_eps: int, n_long: int, n_hit: int, n_all: int, peak_day: str | None, peak_n: int) -> str:
    """기간 요약 문장(숫자 카드 4개 대신)."""
    if not n_eps:
        return f'<p class="jj-sum">{_e(period)}에는 기준을 넘은 이상 구간이 없습니다.</p>'
    s = (f'{_e(period)}에는 읍면동 {n_all}곳 중 <b>{n_hit}곳</b>에서 이상 구간 <b>{n_eps}개</b>가 나왔고, '
         f'그중 <b>{n_long}개</b>는 3일 이상 이어졌습니다.')
    if peak_day:
        s += f' 가장 많은 곳이 함께 달라진 날은 <b>{_e(peak_day)}</b>({peak_n}곳)입니다.'
    return f'<p class="jj-sum">{s}</p>'


def episode_row_html(rank: int, emd: str, span: str, kind: str, up: bool, pct: float, score: float,
                     cause: str, points: list[str], unchecked: str = "") -> str:
    """관제판 TOP 5의 한 줄. 왼쪽 막대와 % 색이 방향(많음 빨강·적음 파랑)을 뜻한다."""
    why = f'<b>{_e(cause)}</b>' + _e(", ".join(points))
    if unchecked:
        why += f'<span class="na">{_e(unchecked)}</span>'
    return (f'<div class="jj-row {"up" if up else "down"}"><div class="rank">{rank}</div>'
            f'<div><div class="name">{_e(emd)}</div><div class="when"><span class="nw">{_e(span)},</span> {_e(kind)}</div></div>'
            f'<div class="pct">{"+" if up else "−"}{abs(pct):.1f}%<small>점수 {abs(score):.1f}</small></div>'
            f'<div class="why">{why}</div></div>')


def evidence_html(rows: list[tuple[str, str]]) -> str:
    """근거 목록. rows = [(상태, 문장)], 상태는 ok(확인됨)·none(기록 없음)·na(확인 불가)."""
    label = {"ok": "확인됨", "none": "기록 없음", "na": "확인 불가"}
    return '<div class="jj-ev">' + "".join(
        f'<div><span class="jj-st {st}">{label[st]}</span><span>{_e(t)}</span></div>' for st, t in rows) + "</div>"


def title_html(emd: str, signal: str, span: str, up: bool, sub: str) -> str:
    """상세 탭 맨 위 제목 문장: 어디의 무엇이 언제 평소보다 많았/적었는지."""
    word = "평소보다 많았던 구간" if up else "평소보다 적었던 구간"
    return (f'<div class="jj-title">{_e(emd)} {_e(signal)}, {_e(span)} '
            f'<span class="{"up" if up else "down"}">{word}</span></div><div class="jj-sub">{_e(sub)}</div>')


def check_html(ok: bool, detail: str) -> str:
    return (f'<div class="jj-check{"" if ok else " fail"}"><b>{"검증 통과" if ok else "검증 미통과"}</b>{_e(detail)}</div>')


def meta_html(items: list[tuple[str, str]]) -> str:
    return '<div class="jj-meta">' + "".join(f"<span><b>{_e(k)}</b>{_e(v)}</span>" for k, v in items) + "</div>"


def answer_html(text: str) -> str:
    """답변 문장: 줄마다 문단, 끝의 [R1][R2] 근거 번호는 작은 위첨자로."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        body = _e(line)
        body = re.sub(r"((?:\[R\d+\])+)", lambda m: "<sup>" + m.group(1).replace("][", ",").strip("[]") + "</sup>", body)
        out.append(f"<p>{body}</p>")
    return '<div class="jj-answer">' + "".join(out) + "</div>"


def table_html(df, num_cols: tuple[str, ...] = ()) -> str:
    """간단한 표(숫자 열은 오른쪽 정렬)."""
    head = "".join(f'<th class="{"n" if c in num_cols else ""}">{_e(c)}</th>' for c in df.columns)
    fmt = lambda v: f"{int(v):,}" if isinstance(v, numbers.Integral) else v   # noqa: E731  정수는 천 단위 쉼표
    body = "".join("<tr>" + "".join(f'<td class="{"n" if c in num_cols else ""}">{_e(fmt(v))}</td>' for c, v in zip(df.columns, row)) + "</tr>"
                   for row in df.itertuples(index=False))
    return f'<table class="jj-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def key_html(items: list[tuple[str, str]]) -> str:
    """색 범례: [(색, 설명), ...]. 색 = 칠한 칸, 'line:색' = 선, 'dot:색' = 점, 'ring' = 흰 바탕 테두리.
    그래프 범례도 이것으로 그려 칸 왼쪽 끝(소제목과 같은 선)에서 시작하게 한다."""
    def swatch(c: str) -> str:
        if c == "ring":
            return '<i class="ring"></i>'
        kind, _, color = c.rpartition(":")
        cls = {"line": ' class="ln"', "dot": ' class="dot"'}.get(kind, "")
        return f'<i{cls} style="background:{color}"></i>'
    return "".join(f'<span class="jj-key">{swatch(c)}{_e(t)}</span>' for c, t in items)


def plot(fig, height: int | None = None):
    """Plotly 차트를 같은 글꼴·선 색으로 맞춘다."""
    fig.update_layout(font=dict(family=FONT, size=12, color=INK_2), paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                      hoverlabel=dict(font_family=FONT, bgcolor="#FFFFFF", bordercolor=LINE_STRONG),
                      legend=dict(orientation="h", y=1.08, x=0, font=dict(size=12)))
    axis_text = dict(tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_xaxes(showgrid=False, linecolor=LINE_STRONG, ticks="outside", tickcolor=LINE_STRONG, **axis_text)
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE_STRONG, linecolor=LINE_STRONG, **axis_text)
    if height:
        fig.update_layout(height=height)
    return fig
