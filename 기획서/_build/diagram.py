import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
plt.rcParams["font.family"] = "Malgun Gothic"

OUT = r"C:\Users\user\AppData\Local\Temp\claude\a44bc184ee130646\5f5664a1-29db-4721-9e8b-ca2bec7c089a\scratchpad\docbuild\workflow.png"
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
ax.set_xlim(0, 100); ax.set_ylim(0, 56); ax.axis("off")

NAVY, TEAL, SAND, GRAY, RED = "#1F3A5F", "#2A7F7F", "#F3EBDD", "#5B6770", "#B5473A"

def box(x, y, w, h, title, sub="", fc="white", ec=NAVY, tc=NAVY, fs=10):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=1.4))
    ax.text(x + w / 2, y + h / 2 + (1.3 if sub else 0), title, ha="center", va="center", fontsize=fs, color=tc, weight="bold")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 1.8, sub, ha="center", va="center", fontsize=7.5, color=GRAY)

def arrow(x1, y1, x2, y2, color=NAVY, text=None, style="-|>"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle=style, color=color, lw=1.4))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.2, text, ha="center", fontsize=7.5, color=color)

# user & UI
box(1, 40, 15, 10, "사용자 질문", "기관 담당자", fc=SAND)
box(1, 6, 15, 10, "브리핑", "표·차트·근거·출처", fc=SAND)
# planner
box(22, 38, 22, 14, "Planner (LLM)", "질문 해석 · 도구 선택·순서", fc=NAVY, tc="white")
ax.texts[-1].set_color("#D9E2EC")
# tools column
tools = [("get_series", "신호 시계열"), ("detect_anomalies", "이상 탐지(2방법)"), ("find_co_movements", "동반 변화"),
         ("check_context", "기상·공휴일·행사"), ("search_docs", "RAG 문서 검색"), ("make_chart", "차트")]
for i, (t, s) in enumerate(tools):
    box(52, 47 - i * 7.6, 20, 6, t, s, fc="white", ec=TEAL, tc=TEAL, fs=8.5)
# data
box(80, 30, 19, 22, "로컬 캐시", "허브 API 수집본\n(DuckDB/parquet)", fc="#E8F1F1", ec=TEAL, tc=TEAL)
box(80, 6, 19, 18, "문서 색인", "데이터 명세·API 문서\n반출 기준·행사 설명", fc="#E8F1F1", ec=TEAL, tc=TEAL)
# writer & verifier
box(22, 20, 22, 10, "Briefing Writer (LLM)", "숫자는 결과 id만 참조")
box(22, 4, 22, 11, "Verifier (코드)", "숫자 일치·출처 실재·근거", fc="white", ec=RED, tc=RED)

arrow(16, 45, 22, 45)
arrow(44, 45, 52, 45, TEAL, "도구 호출")
arrow(72, 41, 80, 41, TEAL)
arrow(72, 19.6, 80, 17, TEAL)
arrow(52, 25, 44, 25, TEAL)
ax.text(48, 22.3, "결과(id)", ha="center", fontsize=7.5, color=TEAL)
arrow(33, 38, 33, 30)
arrow(33, 20, 33, 15)
arrow(22, 9.5, 16, 10, NAVY)
ax.text(19, 7.0, "통과", ha="center", fontsize=7.5, color=NAVY)
ax.annotate("", xy=(23, 38.5), xytext=(23, 15), arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.2, linestyle="--", connectionstyle="arc3,rad=-0.35"))
ax.text(8.5, 27, "검증 실패 시\n재계획\n(최대 2회)", ha="center", fontsize=7.5, color=RED)
plt.savefig(OUT, bbox_inches="tight", facecolor="white")
print(OUT)
