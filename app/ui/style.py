"""화면 스타일(Streamlit에 CSS를 넣는다). 외부 글꼴·파일을 불러오지 않는다(센터 PC는 인터넷이 막혀 있을 수 있음).

한 곳에만 힘을 준다: 탭 줄을 관제실 콘솔 스위치처럼 큰 버튼으로(선택된 탭은 남색에 청록 표시등).
나머지(지표·카드·버튼)는 조용하게 정리만 한다.
"""
from __future__ import annotations

NAVY, TEAL, SAND, RED, INK, LINE = "#1F3A5F", "#2A7F7F", "#F3EBDD", "#B5473A", "#1F2A37", "#CBD5DF"

CSS = f"""
<style>
:root {{ --jj-navy:{NAVY}; --jj-teal:{TEAL}; --jj-sand:{SAND}; --jj-red:{RED}; --jj-ink:{INK}; --jj-line:{LINE}; }}
html, body, [class*="css"] {{ font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }}

/* 머리글 */
.jj-head {{ display:flex; align-items:flex-end; justify-content:space-between; gap:24px; flex-wrap:wrap;
            padding:6px 0 14px; border-bottom:2px solid var(--jj-navy); margin-bottom:18px; }}
.jj-title {{ font-size:2.05rem; font-weight:800; color:var(--jj-navy); letter-spacing:-0.02em; line-height:1.15; }}
.jj-title small {{ display:block; font-size:0.95rem; font-weight:600; color:var(--jj-teal); letter-spacing:0; margin-top:4px; }}
.jj-facts {{ display:flex; gap:18px; flex-wrap:wrap; color:#4A5866; font-size:0.92rem; }}
.jj-facts b {{ color:var(--jj-ink); font-weight:700; margin-left:6px; }}

/* 탭 줄: 콘솔 스위치 */
.stTabs [role="tablist"] {{ gap:12px; border-bottom:none !important; box-shadow:none !important; padding:4px 0 10px; flex-wrap:wrap; }}
.stTabs [role="tablist"]::before, .stTabs [role="tablist"]::after {{ display:none !important; }}
.stTabs [data-testid="stTab"] {{
    min-height:58px; padding:0 26px !important; border:1.5px solid var(--jj-line); border-radius:12px;
    background:#FFFFFF; color:var(--jj-navy) !important; cursor:pointer;
    box-shadow:0 2px 0 var(--jj-line); transition:background .12s, border-color .12s, transform .06s; }}
.stTabs [data-testid="stTab"] p {{ font-size:1.08rem !important; font-weight:700 !important; }}
.stTabs [data-testid="stTab"]:hover {{ border-color:var(--jj-teal); background:#EEF5F5; }}
.stTabs [data-testid="stTab"]:active {{ transform:translateY(1px); box-shadow:0 1px 0 var(--jj-line); }}
.stTabs [data-testid="stTab"][aria-selected="true"] {{
    background:var(--jj-navy); border-color:var(--jj-navy); color:#FFFFFF !important;
    box-shadow:inset 0 -5px 0 var(--jj-teal), 0 2px 0 #13253D; }}
.stTabs [data-testid="stTab"][aria-selected="true"] p, .stTabs [data-testid="stTab"][aria-selected="true"] span {{ color:#FFFFFF !important; }}
.stTabs [data-testid="stTab"]::after, .stTabs [data-testid="stTab"]::before {{ display:none !important; }}
.stTabs [data-testid="stTab"]:focus-visible {{ outline:3px solid var(--jj-teal); outline-offset:2px; }}

/* 지표 */
[data-testid="stMetric"] {{ background:#FFFFFF; border:1px solid #E1E7EE; border-left:4px solid var(--jj-teal);
                           border-radius:8px; padding:10px 14px; }}
[data-testid="stMetricLabel"] p {{ color:#4A5866 !important; font-weight:600; }}
[data-testid="stMetricValue"] {{ color:var(--jj-ink); font-weight:700; font-size:1.75rem !important; }}
.jj-tag {{ display:inline-block; margin-left:6px; padding:1px 7px; border-radius:6px; background:#EEF2F6; color:#4A5866; font-size:0.78rem; font-weight:600; vertical-align:2px; }}

/* 버튼 */
[data-testid="stBaseButton-secondary"] {{ border:1.5px solid var(--jj-teal) !important; color:var(--jj-teal) !important;
                                          font-weight:700 !important; border-radius:8px !important; }}
[data-testid="stBaseButton-secondary"]:hover {{ background:var(--jj-teal) !important; color:#FFFFFF !important; }}
[data-testid="stBaseButton-secondary"]:hover p {{ color:#FFFFFF !important; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
    background:var(--jj-navy) !important; border-color:var(--jj-navy) !important; font-weight:700 !important; border-radius:8px !important; }}

/* 사이드바 */
[data-testid="stSidebar"] {{ background:var(--jj-sand); border-right:1px solid #E4D9C4; }}

@media (prefers-reduced-motion: reduce) {{ .stTabs [data-testid="stTab"] {{ transition:none; }} }}
</style>
"""


def header_html(signal: str, as_of: str, period: str, n_emd: int) -> str:
    return (f'<div class="jj-head"><div class="jj-title">제주 데이터 관제실<small>{signal} 이상 신호</small></div>'
            f'<div class="jj-facts"><span>데이터 기준일<b>{as_of}</b></span><span>분석 기간<b>{period}</b></span>'
            f'<span>읍면동<b>{n_emd}곳</b></span></div></div>')
