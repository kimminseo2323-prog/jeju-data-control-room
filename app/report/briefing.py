"""브리핑 HTML 생성, LLM 없이 쓰는 템플릿 문장, 결과 저장(삭제 ON/OFF)."""
from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

from app.agent.loop import AgentRun

SIGNAL_UNIT = {"유동인구": "명", "와이파이": "명", "버스": "명"}
LIMITS = ("상관관계에 기반한 '원인 후보'이며 인과를 뜻하지 않습니다. "
          "유동인구 값은 하루 시간대별 인구의 합(연인원 성격)입니다.")


def template_text(results: dict) -> str:
    """LLM을 쓸 수 없을 때: 도구 결과만으로 만든 문장(모든 문장에 근거 id)."""
    lines = []
    ctx = {(r.data.get("date"), r.data.get("emd")): (rid, r) for rid, r in results.items() if r.tool == "check_context"}
    for rid, r in results.items():
        if r.tool != "detect_anomalies":
            continue
        d = r.data
        if not d["anomalies"]:
            lines.append(f"{d['emd']} {d['signal']}에서 기준을 넘는 이상 신호는 없었습니다 [{rid}].")
            continue
        lines.append(f"{d['emd']} {d['signal']}에서 이상 신호 {d['count']}건이 확인됐습니다 [{rid}].")
        for a in d["anomalies"][:5]:
            word = "많았" if a["direction"] == "up" else "적었"
            lines.append(f"{a['date']} 값은 {a['value']:,}{SIGNAL_UNIT.get(d['signal'], '')}으로 기대값 {a['expected']:,}보다 "
                         f"{abs(a['pct'])}% {word}습니다 [{rid}].")
            hit = ctx.get((a["date"], d["emd"]))
            if hit and hit[1].data["items"]:
                details = ", ".join(i["detail"] for i in hit[1].data["items"])
                lines.append(f"같은 날 확인된 맥락은 {details}이며 원인 후보로 볼 수 있습니다 [{hit[0]}].")
    return "\n".join(lines)


def _table(data) -> str:
    rows = None
    if isinstance(data, dict):
        for key in ("anomalies", "co_movements", "items", "passages"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    if not rows:
        return ""
    cols = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))[:200]}</td>" for c in cols) + "</tr>" for r in rows[:30])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_briefing(run: AgentRun, generated_at: pd.Timestamp, data_as_of: dict, charts_html: list[str] | None = None) -> str:
    status = "검증 통과" if run.verified else "검증 미통과"
    body = "".join(f"<p>{html.escape(l)}</p>" for l in run.final_text.splitlines() if l.strip())
    body = re.sub(r"\[(R\d+)\]", r'<a href="#\1">[\1]</a>', body)
    asof = "".join(f"<li>{html.escape(k)}: {html.escape(v)}</li>" for k, v in data_as_of.items()) or "<li>-</li>"
    sources = sorted({s for r in run.results.values() for s in r.sources})
    evid = "".join(f'<section id="{rid}"><h3>{rid} · {html.escape(r.tool)}</h3><p class="args">{html.escape(str(r.args))}</p>{_table(r.data)}</section>'
                   for rid, r in run.results.items())
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>제주 데이터 관제실 브리핑</title>
<style>body{{font-family:'Malgun Gothic',sans-serif;max-width:960px;margin:24px auto;color:#1f2a37}}
h1{{color:#1F3A5F}}.badge{{display:inline-block;padding:2px 10px;border-radius:12px;background:{'#2A7F7F' if run.verified else '#B5473A'};color:#fff}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}}th,td{{border:1px solid #cfd8e3;padding:4px 6px}}th{{background:#1F3A5F;color:#fff}}
.muted{{color:#5B6770;font-size:13px}}</style></head><body>
<h1>제주 데이터 관제실 브리핑</h1>
<p class="muted">질문: {html.escape(run.question)} · 생성: {generated_at:%Y-%m-%d %H:%M} · <span class="badge">{status}</span></p>
<h2>요약</h2>{body}
{''.join(charts_html or [])}
<h2>데이터 기준일</h2><ul>{asof}</ul>
<h2>근거</h2>{evid}
<h2>출처</h2><ul>{''.join(f'<li>{html.escape(s)}</li>' for s in sources)}</ul>
<h2>한계</h2><p class="muted">{LIMITS}</p>
</body></html>"""


class ResultStore:
    """결과 저장. delete_on_exit=True면 세션 종료(cleanup) 때 저장한 파일을 지운다(센터 퇴실 시 삭제 원칙)."""

    def __init__(self, root: Path | str, delete_on_exit: bool = True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.delete_on_exit = delete_on_exit
        self.saved: list[Path] = []

    def save(self, name: str, content: str, ext: str = "html") -> Path:
        p = self.root / f"{name}_{pd.Timestamp.now():%Y%m%d_%H%M%S}.{ext}"
        p.write_text(content, "utf-8")
        self.saved.append(p)
        return p

    def cleanup(self) -> None:
        if self.delete_on_exit:
            for p in self.saved:
                p.unlink(missing_ok=True)
            self.saved.clear()
