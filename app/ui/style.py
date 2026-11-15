"""화면 스타일. 기준: docs/디자인_기준.md (IBM Carbon 구조 + 출발 안내판식 신호색).

- 구조: 각진 모서리, 1px 선, 흰색·연회색(#F4F4F4) 면 단계. 그림자·그라데이션·둥근 카드는 쓰지 않는다.
- 색은 뜻이 있을 때만: 빨강 = 평소보다 많음, 파랑 = 평소보다 적음, 귤색 = 지금 고른 것(탭·구간). 나머지는 현무암 먹색과 회색.
- 힘을 주는 곳은 하나: 맨 위 현무암색 상황판 띠. 나머지는 조용하게.
- 글꼴은 app/ui/static/fonts 의 IBM Plex Sans KR(OFL)을 이 PC에서 내보낸다(외부 글꼴 서버를 부르지 않음).
"""
from __future__ import annotations

import html

INK, INK_2, MUTED, SUBTLE = "#161616", "#393939", "#525252", "#8D8D8D"
LEDGER, LINE, LINE_STRONG = "#F4F4F4", "#E0E0E0", "#C6C6C6"
UP, DOWN, PICK = "#DA1E28", "#0043CE", "#E8630A"   # 많음 · 적음 · 지금 고른 것(감귤색)
FONT = "IBM Plex Sans KR, Malgun Gothic, sans-serif"

CSS = f"""
<style>
:root {{ --jj-ink:{INK}; --jj-ink2:{INK_2}; --jj-muted:{MUTED}; --jj-subtle:{SUBTLE}; --jj-ledger:{LEDGER};
        --jj-line:{LINE}; --jj-line-strong:{LINE_STRONG}; --jj-up:{UP}; --jj-down:{DOWN}; --jj-pick:{PICK}; }}
.block-container {{ padding-top:3.6rem; }}
p, li, label, .stMarkdown {{ letter-spacing:0.16px; }}
h4 {{ font-weight:600 !important; font-size:1.05rem !important; color:var(--jj-ink); padding:0 0 6px !important;
      border-bottom:1px solid var(--jj-line); margin:22px 0 10px !important; }}

/* 상황판 띠: 이 화면에서 유일하게 어두운 면 */
.jj-board {{ display:grid; grid-template-columns:minmax(260px, 1.4fr) repeat(3, minmax(120px, 1fr)); background:var(--jj-ink);
            color:#FFFFFF; margin:0 0 2px; }}
.jj-board > div {{ padding:16px 20px; border-left:1px solid var(--jj-ink2); }}
.jj-board > div:first-child {{ border-left:none; }}
.jj-board .t {{ font-size:1.9rem; font-weight:300; line-height:1.15; letter-spacing:-0.2px; }}
.jj-board .s {{ display:flex; align-items:center; gap:8px; margin-top:6px; font-size:0.95rem; color:#C6C6C6; }}
.jj-board .s::before {{ content:""; width:8px; height:8px; background:var(--jj-pick); display:inline-block; }}
.jj-board .k {{ font-size:0.78rem; color:#A8A8A8; letter-spacing:0.32px; }}
.jj-board .v {{ font-size:1.35rem; font-weight:300; margin-top:4px; font-variant-numeric:tabular-nums; }}
@media (max-width: 900px) {{ .jj-board {{ grid-template-columns:1fr 1fr; }} .jj-board > div:first-child {{ grid-column:1 / -1; }} }}

/* 탭: Carbon 'contained tabs' — 붙어 있는 큰 칸, 고른 칸은 흰 바탕에 위쪽 귤색 막대 */
.stTabs [role="tablist"] {{ gap:2px; border-bottom:none !important; box-shadow:none !important; flex-wrap:wrap; }}
.stTabs [role="tablist"]::before, .stTabs [role="tablist"]::after {{ display:none !important; }}
.stTabs [data-testid="stTab"] {{
    flex:1 1 180px; min-height:56px; padding:0 20px !important; justify-content:flex-start;
    background:{LINE}; color:{MUTED} !important; border:none; border-radius:0; border-top:3px solid transparent; border-bottom:none !important;
    cursor:pointer; transition:background .1s; }}
.stTabs [data-testid="stTab"] p {{ font-size:1.02rem !important; font-weight:400 !important; }}
.stTabs [data-testid="stTab"]:hover {{ background:{LINE_STRONG}; color:{INK} !important; }}
.stTabs [data-testid="stTab"][aria-selected="true"] {{ background:#FFFFFF; color:{INK} !important; border-top-color:var(--jj-pick); }}
.stTabs [data-testid="stTab"][aria-selected="true"] p {{ font-weight:600 !important; }}
.stTabs [data-testid="stTab"]::after, .stTabs [data-testid="stTab"]::before {{ display:none !important; }}
.stTabs [data-testid="stTab"]:focus-visible {{ outline:2px solid {INK}; outline-offset:-2px; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none !important; }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top:20px; }}

/* 지표: 연회색 칸, 숫자는 가는 글씨(Carbon의 300 굵기) */
[data-testid="stMetric"] {{ background:var(--jj-ledger); padding:14px 16px 12px; }}
[data-testid="stMetricLabel"] p {{ color:var(--jj-muted) !important; font-size:0.82rem !important; }}
[data-testid="stMetricValue"] {{ color:var(--jj-ink); font-weight:300 !important; font-size:1.7rem !important; font-variant-numeric:tabular-nums; }}

/* 이상 구간 줄: 왼쪽 막대 색 = 방향(많음/적음) */
.jj-row {{ display:grid; grid-template-columns:44px minmax(150px, 1.5fr) minmax(110px, 0.9fr) minmax(200px, 3fr);
          border:1px solid var(--jj-line); border-left:4px solid var(--jj-subtle); background:#FFFFFF; }}
.jj-row.up {{ border-left-color:var(--jj-up); }} .jj-row.down {{ border-left-color:var(--jj-down); }}
.jj-row > div {{ padding:12px 14px; }}
.jj-row .rank {{ font-size:1.4rem; font-weight:300; color:var(--jj-subtle); padding-right:0; }}
.jj-row .where b {{ font-weight:600; font-size:1.02rem; }}
.jj-row .where span, .jj-row .pct small, .jj-row .why .r {{ display:block; color:var(--jj-muted); font-size:0.84rem; margin-top:2px; }}
.jj-row .pct b {{ font-weight:300; font-size:1.6rem; font-variant-numeric:tabular-nums; }}
.jj-row.up .pct b {{ color:var(--jj-up); }} .jj-row.down .pct b {{ color:var(--jj-down); }}
.jj-row .why b {{ font-weight:600; }}
.jj-tag {{ display:inline-block; margin-left:8px; padding:0 6px; border:1px solid var(--jj-line-strong); color:var(--jj-muted);
          font-size:0.74rem; font-weight:400; vertical-align:2px; }}
@media (max-width: 900px) {{ .jj-row {{ grid-template-columns:36px 1fr 1fr; }} .jj-row .why {{ grid-column:1 / -1; border-top:1px solid var(--jj-line); }} }}

/* 범례 칩(지도·차트 설명) */
.jj-key {{ display:inline-flex; align-items:center; gap:6px; margin-right:14px; color:var(--jj-muted); font-size:0.84rem; }}
.jj-key i {{ width:10px; height:10px; display:inline-block; border-radius:50%; }}

/* 버튼: 기본은 먹색 테두리, 주요 동작은 먹색 채움 */
[data-testid="stBaseButton-secondary"] {{ border:1px solid {INK} !important; color:{INK} !important; background:#FFFFFF !important; }}
[data-testid="stBaseButton-secondary"]:hover {{ background:{INK} !important; color:#FFFFFF !important; }}
[data-testid="stBaseButton-secondary"]:hover p {{ color:#FFFFFF !important; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{ background:{INK} !important; border-color:{INK} !important; }}

[data-testid="stSidebar"] {{ border-right:1px solid var(--jj-line); }}
[data-testid="stExpander"] details {{ border-radius:0; border-color:var(--jj-line); }}
@media (prefers-reduced-motion: reduce) {{ .stTabs [data-testid="stTab"] {{ transition:none; }} }}
</style>
"""


def header_html(signal: str, as_of: str, period: str, n_emd: int) -> str:
    """맨 위 상황판 띠: 화면 이름·지금 보는 신호 / 데이터 기준일 / 분석 기간 / 읍면동 수."""
    e = html.escape
    return (f'<div class="jj-board"><div><div class="t">제주 데이터 관제실</div><div class="s">{e(signal)} 이상 신호</div></div>'
            f'<div><div class="k">데이터 기준일</div><div class="v">{e(as_of)}</div></div>'
            f'<div><div class="k">분석 기간</div><div class="v">{e(period)}</div></div>'
            f'<div><div class="k">읍면동</div><div class="v">{n_emd}곳</div></div></div>')


def episode_row_html(rank: int, emd: str, span: str, kind: str, up: bool, pct: float, score: float, cause: str, reason: str) -> str:
    """관제판 TOP 5의 한 줄. 왼쪽 막대와 % 색이 방향(많음 빨강·적음 파랑)을 뜻한다."""
    e = html.escape
    return (f'<div class="jj-row {"up" if up else "down"}"><div class="rank">{rank}</div>'
            f'<div class="where"><b>{e(emd)}</b><span>{e(span)}</span><span>{e(kind)}</span></div>'
            f'<div class="pct"><b>{"+" if up else "−"}{abs(pct)}%</b><small>기대값 대비, 점수 {score}</small></div>'
            f'<div class="why"><b>{e(cause)}</b><span class="jj-tag">빠른 판정</span><span class="r">{e(reason)}</span></div></div>')


def key_html(items: list[tuple[str, str]]) -> str:
    """색 범례: [(색, 설명), ...]"""
    return "".join(f'<span class="jj-key"><i style="background:{c}"></i>{html.escape(t)}</span>' for c, t in items)


def plot(fig, height: int | None = None):
    """Plotly 차트를 같은 글꼴·선 색으로 맞춘다."""
    fig.update_layout(font=dict(family=FONT, size=12, color=INK_2), paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                      hoverlabel=dict(font_family=FONT, bgcolor="#FFFFFF", bordercolor=LINE_STRONG),
                      legend=dict(orientation="h", y=1.08, x=0, font=dict(size=12)))
    fig.update_xaxes(showgrid=False, linecolor=LINE_STRONG, ticks="outside", tickcolor=LINE_STRONG)
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE_STRONG, linecolor=LINE_STRONG)
    if height:
        fig.update_layout(height=height)
    return fig
