"""기획서 v0.2 Workflow 그림. 실행: python 기획서/_build/diagram_v2.py → 기획서/_build/workflow_v2.png"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from matplotlib import font_manager

# 디자인 기준(docs/디자인_기준.md): 각진 상자, 먹색·회색 단계, 판단 모델 상자만 먹색 채움, 글꼴 IBM Plex Sans KR
FONTS = Path(__file__).with_name("fonts")
for f in FONTS.glob("*.ttf"):
    font_manager.fontManager.addfont(str(f))
plt.rcParams["font.family"] = "IBM Plex Sans KR" if any(FONTS.glob("*.ttf")) else "Malgun Gothic"
OUT = Path(__file__).with_name("workflow_v2.png")
NAVY, TEAL, SAND, GRAY, RED, LT = "#161616", "#525252", "#F4F4F4", "#525252", "#161616", "#F4F4F4"

fig, ax = plt.subplots(figsize=(10, 6.2), dpi=200)
ax.set_xlim(0, 100); ax.set_ylim(0, 62); ax.axis("off")


def box(x, y, w, h, title, sub="", fc="white", ec=NAVY, tc=NAVY, fs=9.5, sc=GRAY):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0.35", fc=fc, ec=ec, lw=1.3))
    n = sub.count("\n") + 1 if sub else 0
    if n > 2:   # 여러 줄 설명: 제목은 위, 설명은 그 아래로
        ax.text(x + w / 2, y + h - 2.6, title, ha="center", va="center", fontsize=fs, color=tc, weight="bold")
        ax.text(x + w / 2, y + h - 5.0, sub, ha="center", va="top", fontsize=7.2, color=sc, linespacing=1.5)
        return
    ax.text(x + w / 2, y + h / 2 + (1.25 if sub else 0), title, ha="center", va="center", fontsize=fs, color=tc, weight="bold")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 1.6, sub, ha="center", va="center", fontsize=7.2, color=sc)


def arrow(x1, y1, x2, y2, color=NAVY, text=None, dx=0, dy=1.0, ls="-"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3, linestyle=ls))
    if text:
        ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2 + dy, text, ha="center", fontsize=7, color=color)


# 사용자
box(1, 49, 17, 9, "질문하기 탭", "\"○○동 ○월 ○일에 왜?\"", fc=SAND)
box(1, 33, 17, 9, "관제판·상세 분석", "이상 구간 클릭", fc=SAND)
box(1, 3, 17, 10, "답변·브리핑", "숫자마다 근거 [R1]", fc=SAND)

# 파이프라인(가운데)
X, Wd = 25, 30
box(X, 50, Wd, 8, "① 질문 분류", "tev1:4b (로컬) + 규칙 보완 · 범위 밖 안내", fc=NAVY, tc="white", sc="#D9E2EC")
box(X, 40.5, Wd, 7, "② 조건 추출 (규칙)", "읍면동·날짜·기간·신호")
box(X, 30, Wd, 8, "③ 도구 실행 (정해진 순서)", "결과마다 id(R1, R2…) 부여", ec=TEAL, tc=TEAL)
box(X, 20.5, Wd, 7, "④ 원인 판정", "tev1:4b · 근거 문장만 보고 확률 산출", fc=NAVY, tc="white", sc="#D9E2EC")
box(X, 11.5, Wd, 6.5, "⑤ 문장 작성 (템플릿)", "결과 id를 인용한 문장만")
box(X, 2, Wd, 7, "⑥ 검증기 (코드)", "숫자·날짜·근거 id·원인 표현 대조", ec="#E8630A", tc=NAVY)

for y1, y2 in [(50, 47.5), (40.5, 38), (30, 27.5), (20.5, 18), (11.5, 9)]:
    arrow(X + Wd / 2, y1, X + Wd / 2, y2)
arrow(18, 53.5, X, 54)
arrow(18, 37.5, X, 34)
ax.text(9.5, 29.6, "지역·날짜가 정해져\n③부터 실행", ha="center", fontsize=7, color=NAVY)
arrow(X, 5.5, 18, 7, NAVY, "통과", dy=0.8)
ax.text(21.5, 17, "실패 시\n답변 보류", ha="center", fontsize=7, color=RED)

# 도구(오른쪽)
tools = [("detect_anomalies", "이상일·구간 탐지"), ("scan_regions", "43개 읍면동 훑기"), ("find_co_movements", "다른 신호·제주 전체·인근"),
         ("check_context", "기상·공휴일·행사·입도객·작년"), ("nationality_mix", "외국인 국적별 변화"),
         ("search_docs", "문서 검색(BM25)"), ("get_series", "시계열 조회")]
for i, (t, s) in enumerate(tools):
    box(61, 54 - i * 6.1, 19, 4.4, t, s, ec=TEAL, tc=TEAL, fs=8)
arrow(X + Wd, 34, 61, 34, TEAL)

# 데이터(오른쪽 끝)
box(84, 33, 15, 25, "로컬 캐시", "허브 Open API\n수집본(parquet)\n유동인구(내·외국인)\n와이파이·버스\n기상·입도객\n정류소·AP 위치", fc=LT, ec=TEAL, tc=TEAL)
box(84, 14, 15, 15, "문서 색인", "데이터 명세서\n허브 API 문서\n반출 기준·게시판", fc=LT, ec=TEAL, tc=TEAL)
box(62, 4, 36, 6, "Ollama (127.0.0.1:11434)", "tev1:4b · 없으면 규칙 기반으로 자동 대체", fc="white", ec=NAVY, tc=NAVY, fs=8.5)
arrow(80, 45, 84, 45, TEAL)
arrow(80, 25.5, 84, 25.5, TEAL)
ax.text(80, 0.2, "외부 LLM·외부 서버로 데이터를 보내지 않음", ha="right", fontsize=7.2, color=RED)

plt.savefig(OUT, bbox_inches="tight", facecolor="white")
print(OUT)
