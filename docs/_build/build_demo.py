"""결과 데모(GitHub Pages) 자료 만들기.

실제 화면(app/ui/app.py)을 Streamlit AppTest로 실행해, 화면이 그린 그래프(Plotly 그림)와 문장(HTML)을 그대로 꺼내
docs/demo/data/*.json 으로 저장한다. 데모 페이지(docs/index.html)는 이 파일을 읽어 같은 그림을 다시 그린다.
그래서 데모의 숫자·문장은 제출본 프로그램이 계산한 것과 같다(유동인구 신호, 같은 요일 중앙값, 민감도 3.5).

실행(프로젝트 폴더에서, 판단 모델 서버가 켜져 있을 때):
    JUDGE_HOST=http://127.0.0.1:11501 python docs/_build/build_demo.py              (전체, 약 25분)
    JUDGE_HOST=http://127.0.0.1:11501 python docs/_build/build_demo.py --asks-only  (질문 예시만)
JUDGE_HOST를 꼭 지정한다. 원인 판정은 그 주소의 tev1이 하고, 연결되지 않으면 규칙 판정이 들어간다(화면에 그렇게 표시됨).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "demo" / "data"
ASK_EXTRA = ["성산읍 2024년 9월 16일에 유동인구가 왜 늘었어?", "이호동 2024년 8월 2일에 사람이 왜 많았어?", "오늘 점심 메뉴 추천해줘"]


def _fig(chart) -> dict:
    spec = json.loads(chart.proto.spec)
    return {"data": spec["data"], "layout": spec["layout"], "config": json.loads(chart.proto.config or "{}")}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")


def main() -> None:
    if not os.environ.get("JUDGE_HOST"):
        sys.exit("JUDGE_HOST를 지정하세요(예: http://127.0.0.1:11501). 기본 포트로는 보내지 않습니다.")
    sys.path.insert(0, str(ROOT))
    from streamlit.testing.v1 import AppTest

    t0 = time.time()
    at = AppTest.from_file(str(ROOT / "app" / "ui" / "app.py"), default_timeout=600).run()
    assert not at.exception, [e.message for e in at.exception]
    css = re.sub(r"^\s*<style>|</style>\s*$", "", at.markdown[0].value.strip())
    (ROOT / "docs" / "demo").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "demo" / "app.css").write_text(css, "utf-8")
    header = at.markdown[1].value
    model = next(c.value for c in at.sidebar.caption if c.value.startswith("원인 판정 모델:"))

    period = next(s for s in at.selectbox if s.label == "기간")
    months = list(period.options)
    eps: dict[int, str] = {}
    for m in months:
        next(s for s in at.selectbox if s.label == "기간").set_value(m).run()
        assert not at.exception, (m, [e.message for e in at.exception])
        tab = at.tabs[0]
        md = [x.value for x in tab.markdown]
        charts = tab.get("plotly_chart")
        rows = [v for v in md if v.startswith('<div class="jj-row')]
        go = [int(b.key.split("_")[1]) for b in tab.button if (b.key or "").startswith("go_")]
        _write(OUT / "board" / f"{'all' if m == '전체 기간' else m}.json", {
            "summary": next((v for v in md if 'class="jj-sum"' in v), ""),
            "rows": [{"html": h, "ep": i} for h, i in zip(rows, go)],
            "map_key": next((v for v in md if v.startswith('<span class="jj-key"')), ""),
            "captions": [c.value for c in tab.caption],
            "map": _fig(charts[0]) if len(charts) > 1 else None,
            "when": _fig(charts[1]) if len(charts) > 1 else None,
        })
        eps.update({i: "" for i in go})
        print(f"관제판 {m}: TOP {len(rows)} ({time.time() - t0:.0f}s)", flush=True)

    pick = next(s for s in at.tabs[1].selectbox if s.label.startswith("이상 구간"))
    labels = list(pick.options)
    for n, i in enumerate(sorted(eps), 1):
        next(s for s in at.tabs[1].selectbox if s.label.startswith("이상 구간")).select_index(i).run()
        next(b for b in at.tabs[1].button if b.label == "원인 판정 실행").click().run()
        assert not at.exception, (i, [e.message for e in at.exception])
        tab = at.tabs[1]
        md = [x.value for x in tab.markdown]
        charts = [_fig(c) for c in tab.get("plotly_chart")]
        sec = {}   # '#### 제목' 뒤에 오는 문단들을 제목별로 묶는다
        cur = "title"
        for v in md:
            if v.startswith("#### "):
                cur = v[5:].strip()
                continue
            sec.setdefault(cur, []).append(v)
        _write(OUT / "detail" / f"{i}.json", {
            "label": labels[i], "sections": sec, "captions": [c.value for c in tab.caption],
            "trend": charts[0] if charts else None, "location": charts[1] if len(charts) > 1 else None,
            "judge": charts[2] if len(charts) > 2 else None,
            "evidence_text": [t.value for t in tab.get("text")],
        })
        eps[i] = labels[i]
        print(f"상세 {n}/{len(eps)} {labels[i]} ({time.time() - t0:.0f}s)", flush=True)

    asks = ask_all(at, t0)

    _write(OUT / "index.json", {"generated": time.strftime("%Y-%m-%d %H:%M"), "header": header, "model": model,
                                "months": months, "episodes": {str(k): v for k, v in sorted(eps.items())}, "asks": asks})
    print(f"끝: 기간 {len(months)}개, 상세 {len(eps)}개, 질문 {len(asks)}개, {time.time() - t0:.0f}초")


def ask_all(at, t0: float) -> list[dict]:
    """질문하기 탭: 화면의 예시 질문(st.pills라 버튼으로 잡히지 않음) + ASK_EXTRA를 차례로 넣고 답을 모은다."""
    questions = [o for o in at.tabs[2].get("button_group")[0].options] if at.tabs[2].get("button_group") else []
    questions = [getattr(q, "content", q) for q in questions] + ASK_EXTRA
    asks = []
    for q in questions:
        at.session_state["ask_hist"] = []
        at.tabs[2].text_input[0].set_value(q)
        next(b for b in at.tabs[2].button if b.label == "질문 보내기").click().run()
        assert not at.exception, (q, [e.message for e in at.exception])
        md = [x.value for x in at.tabs[2].markdown]
        start = md.index(f"**{q}**")
        block = [v for v in md[start + 1:] if not re.match(r"\*\*R\d+\. ", v)]
        refs = [v for v in md[start + 1:] if re.match(r"\*\*R\d+\. ", v)]
        if any("search_docs" in r for r in refs):
            # 문서 질문의 답은 허브 문서·게시판 답변 원문 조각을 인용한다. 게시판 답변(11/9): 외부 공개 시엔 원문 대신 출처·링크
            print(f"질문(공개 데모에서 뺌, 문서 원문 인용): {q}", flush=True)
            continue
        asks.append({"q": q, "html": block, "refs": refs})
        print(f"질문: {q} ({time.time() - t0:.0f}s)", flush=True)
    return asks


def asks_only() -> None:
    """질문 예시만 다시 만든다(index.json의 asks만 바꿈)."""
    sys.path.insert(0, str(ROOT))
    from streamlit.testing.v1 import AppTest
    t0 = time.time()
    at = AppTest.from_file(str(ROOT / "app" / "ui" / "app.py"), default_timeout=600).run()
    idx = json.loads((OUT / "index.json").read_text("utf-8"))
    idx["asks"] = ask_all(at, t0)
    _write(OUT / "index.json", idx)
    print(f"질문 {len(idx['asks'])}개 다시 만듦")


if __name__ == "__main__":
    if not os.environ.get("JUDGE_HOST"):
        sys.exit("JUDGE_HOST를 지정하세요(예: http://127.0.0.1:11501). 기본 포트로는 보내지 않습니다.")
    asks_only() if "--asks-only" in sys.argv else main()
