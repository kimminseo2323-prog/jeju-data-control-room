"""로컬 에이전트: 외부 LLM 없이 질문에 답한다.

1) 질문 분류: 로컬 판단 모델(tev1)이 scan/explain/docs/other 중 고른다. 연결이 안 되면 키워드 규칙.
2) 슬롯 추출: 읍면동·날짜·기간·신호를 규칙으로 뽑는다(모델이 숫자·지명을 지어내지 않도록).
3) 정해진 도구 흐름 실행 → 템플릿 문장(모든 숫자에 근거 id) → 검증기 통과 시에만 표시.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd
import requests

from app.agent.loop import WITHHELD, AgentRun
from app.agent.tools import ToolError, ToolResult, Toolbox
from app.agent.verify import verify
from app.analytics.context import KR_HOLIDAYS
from app.llm.judge import CAUSE_KO, CONNECT_TIMEOUT, DEFAULT_HOST, DEFAULT_MODEL, Judgment, evidence_text, judge_cause, local_model_ready
from app.report.briefing import template_text
from app.store.geo import EMD_43

INTENTS = {
    "scan": "특정 기간·지역·신호에서 이상 신호가 어디서 언제 있었는지 찾아 달라는 질문이다.",
    "explain": "특정 지역(과 날짜)의 이상 신호가 왜 생겼는지, 원인을 설명해 달라는 질문이다.",
    "docs": "데이터의 출처·정의·컬럼·수집 기준·반출 규정 등 문서 내용을 묻는 질문이다.",
    "other": "제주 관광·교통 데이터 분석과 관계없는 질문이다.",
}
INTENT_KO = {"scan": "이상 찾기", "explain": "원인 설명", "docs": "문서 검색", "other": "범위 밖"}

SCOPE_TEXT = ("이 질문은 다루지 않습니다. 이 도우미는 제주 관광·교통 데이터의 이상 신호 찾기, 변화 이유 후보 설명, "
              "데이터 문서 검색만 답합니다. 예: '유동인구가 이상했던 곳 알려줘', '이호동 유동인구가 왜 늘었어?', '버스 데이터 출처가 뭐야?'")
ASK_REGION = "어느 읍면동인지 함께 적어 주세요. 예: '이호동 유동인구가 왜 늘었어?'"
BAD_DATE = "질문에 적은 날짜가 달력에 없는 날짜입니다. 날짜를 확인해 다시 물어봐 주세요."

_RULES = [
    ("explain", re.compile(r"왜|원인|이유|때문")),
    ("docs", re.compile(r"출처|정의|뜻|의미|컬럼|명세|API|api|반출|쿼터|수집 기준|가져온|데이터셋|문서")),
    ("scan", re.compile(r"이상|급증|급감|많았|적었|어디|언제|목록|찾아|튄")),
]
_SIGNALS = [("외국인", re.compile(r"외국인|해외|중국인|일본인|크루즈")), ("와이파이", re.compile(r"와이파이|wifi|WiFi|WIFI")),
            ("버스", re.compile(r"버스|승차|정류"))]
_EUP_MYEON_STEMS = {full.split(" ")[1][:-1]: full for full in EMD_43 if full.endswith(("읍", "면"))}


@dataclass
class Slots:
    emd: str | None = None
    signal: str = "유동인구"
    date: pd.Timestamp | None = None
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None
    bad_date: str | None = None   # 달력에 없는 날짜(예: 2월 30일, 13월)를 적은 경우 그 표현


@dataclass
class LocalRun(AgentRun):
    intent: str = ""
    intent_prob: float = 0.0
    router: str = ""
    slots: Slots | None = None


# ---------------- 슬롯 ----------------
def _year_for(month: int, day: int, lo: pd.Timestamp, hi: pd.Timestamp) -> int:
    """연도 없는 날짜는 데이터 기간 안의 가장 최근 해로 본다(2024-04~2026-08이면 '7월 28일' → 2026-07-28)."""
    for y in range(hi.year, lo.year - 1, -1):
        try:
            if lo <= pd.Timestamp(y, month, day) <= hi:
                return y
        except ValueError:
            continue
    return hi.year


def _find_emd(q: str) -> str | None:
    aliases = [(full, full) for full in EMD_43] + [(full.split(" ")[1], full) for full in EMD_43] + list(_EUP_MYEON_STEMS.items())
    for alias, full in sorted(aliases, key=lambda a: -len(a[0])):
        if alias in q:
            return full
    return None


def parse_slots(q: str, lo: pd.Timestamp, hi: pd.Timestamp) -> Slots:
    s = Slots(emd=_find_emd(q))
    for name, pat in _SIGNALS:
        if pat.search(q):
            s.signal = name
            break

    m = re.search(r"(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})", q)
    if m:
        try:
            s.date = pd.Timestamp(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            s.bad_date = m[0]
        return s
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일|(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", q)
    if m:
        mo, d = (int(m[1]), int(m[2])) if m[1] else (int(m[3]), int(m[4]))
        try:
            s.date = pd.Timestamp(_year_for(mo, d, lo, hi), mo, d)
        except ValueError:
            s.bad_date = m[0]
        return s
    m = re.search(r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(초|중순|말)?", q)
    if m:
        mo = int(m[2])
        if not 1 <= mo <= 12:
            s.bad_date = m[0]
            return s
        y = int(m[1]) if m[1] else _year_for(mo, 1, lo, hi)
        first = pd.Timestamp(y, mo, 1)
        last = first + pd.offsets.MonthEnd(0)
        part = {"초": (1, 10), "중순": (11, 20), "말": (21, last.day)}.get(m[3] or "")
        s.start, s.end = (first.replace(day=part[0]), first.replace(day=part[1])) if part else (first, last)
        return s
    # 공휴일 이름(어린이날, 설날 등): 데이터 기간 안에서 가장 긴 이름이 맞는 날짜 중 가장 최근
    best = None
    for d, name in sorted(KR_HOLIDAYS.items()):
        ts = pd.Timestamp(d)
        if lo <= ts <= hi and name in q and (best is None or len(name) >= len(best[1])):
            best = (ts, name)
    if best:
        s.date = best[0]
    return s


# ---------------- 분류 ----------------
def rule_route(q: str) -> str:
    for intent, pat in _RULES:
        if pat.search(q):
            return intent
    return "other"


def route(q: str, http=requests, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL) -> tuple[str, float, str]:
    if not local_model_ready(http, host, model):   # 확인된 로컬 모델이 아니면 질문을 보내지 않는다
        return rule_route(q), 0.0, "rule"
    body = {"model": model, "state": f"사용자 질문: {q}", "questions": {"intent": {
        "type": "choice", "instructions": "Classify the user's question to a Jeju tourism/transport anomaly dashboard assistant.",
        "criteria": INTENTS}}}
    try:
        r = http.post(f"{host}/v1/systemone", json=body, timeout=(CONNECT_TIMEOUT, 60))
        r.raise_for_status()
        ans = r.json()["answers"]["intent"]
        if ans.get("choice") not in INTENTS:
            raise ValueError(ans)
    except Exception:
        return rule_route(q), 0.0, "rule"
    # 모델이 '범위 밖'이라 했는데 키워드가 분석 질문을 가리키면 규칙을 따른다
    # (범위 안 질문을 거절하는 쪽이 범위 밖 질문에 분석 결과를 보여 주는 쪽보다 나쁘다고 판단)
    if ans["choice"] == "other" and (rule := rule_route(q)) != "other":
        return rule, 0.0, f"{model}+rule"
    return ans["choice"], float(ans.get("probabilities", {}).get(ans["choice"], ans.get("confidence", 0))), model


# ---------------- 흐름 ----------------
def _data_range(store) -> tuple[pd.Timestamp, pd.Timestamp]:
    idx = [store.island_series(s).dropna().index for s in store.signals()]
    idx = [i for i in idx if len(i)]
    if not idx:
        return pd.Timestamp("2024-04-01"), pd.Timestamp("2025-03-31")
    return min(i.min() for i in idx), max(i.max() for i in idx)


def _d(ts) -> str | None:
    return str(ts.date()) if ts is not None else None


class _Calls:
    def __init__(self, tb: Toolbox):
        self.tb, self.results = tb, {}

    def __call__(self, name: str, args: dict) -> tuple[str, ToolResult]:
        rid = f"R{len(self.results) + 1}"
        self.results[rid] = self.tb.dispatch(name, args, rid)
        return rid, self.results[rid]


def _explain(q, s: Slots, tb: Toolbox, judge, method, threshold) -> tuple[str, dict]:
    if not s.emd:
        return ASK_REGION, {}
    call = _Calls(tb)
    if s.date is not None:
        start, end = s.date - pd.Timedelta(days=14), s.date + pd.Timedelta(days=14)
    else:
        start, end = s.start, s.end
    r1, det = call("detect_anomalies", {"signal": s.signal, "emd": s.emd, "start": _d(start), "end": _d(end),
                                        "method": method, "threshold": threshold})
    eps = det.data["episodes"]
    if s.date is not None:
        day = str(s.date.date())
        eps = [e for e in eps if e["start"] <= day <= e["end"]] or \
              [e for e in eps if abs((pd.Timestamp(e["peak_date"]) - s.date).days) <= 3]
    if not eps:
        return template_text(call.results), call.results
    ep = max(eps, key=lambda e: abs(e["peak_score"]))
    day = ep["peak_date"]
    r2, co = call("find_co_movements", {"date": day, "emd": s.emd, "window": 1, "exclude_signal": s.signal})
    r3, cx = call("check_context", {"date": day, "emd": s.emd, "signal": s.signal})
    shown = {r1: det, r2: co, r3: cx}
    if s.signal == "외국인":   # 어느 국적이 변화를 이끌었는지(화면·답변용, 판정 근거에는 넣지 않음)
        try:
            rn, nm = call("nationality_mix", {"date": day, "emd": s.emd})
            shown[rn] = nm
        except ToolError:
            pass
    evidence = {"anomaly": {"emd": s.emd, "signal": s.signal, "date": day, "pct": ep["peak_pct"], "kind": ep["kind"], "days": ep["days"]},
                "context": cx.data["items"], "co_movements": co.data["co_movements"], "not_covered": cx.data.get("not_covered", []),
                "co_checked": co.data["checked"], "co_no_data": co.data.get("no_data", [])}
    j = judge(evidence)
    return add_judgment(template_text(shown), call.results, j, evidence, refs=[r2, r3]), call.results


def add_judgment(text: str, results: dict, j: Judgment, evidence: dict, refs: list[str]) -> str:
    """원인 판정을 결과 묶음에 새 id로 넣고, 판정 문장과 '인과 아님' 문장을 text 뒤에 붙인다.
    질문하기(원인 설명)와 상세 분석 탭 브리핑이 같은 문장을 쓴다. refs = 판정 근거가 된 결과 id(동반 변화·맥락)."""
    rid = f"R{len(results) + 1}"
    prob = round(j.probabilities.get(j.choice, 0) * 100, 1)
    results[rid] = ToolResult(rid, "judge_cause", {"evidence": evidence_text(evidence)},
                              {"choice": j.choice, "choice_ko": CAUSE_KO[j.choice], "probability": prob, "level": j.level,
                               "backend": j.backend, "note": j.note,
                               "probabilities": {k: round(v * 100, 1) for k, v in j.probabilities.items()}},
                              [f"로컬 판단 모델 {j.backend}" if j.backend != "rule" else "규칙 기반 판정(로컬 판단 모델 연결 실패)"])
    cite = "".join(f"[{r}]" for r in [rid, *refs])
    # 문장은 템플릿이 만든다. 원인 후보를 고른 주체를 밝히고, 규칙일 때는 고정 확률(75%)을 보이지 않는다
    sentence = (f"판단 모델({j.backend.split(':')[0]})이 근거를 보고 고른 원인 후보는 '{CAUSE_KO[j.choice]}'(확률 {prob:.1f}%, 확신도 {j.level})입니다 {cite}."
                if j.backend != "rule" else
                f"규칙으로 고른 원인 후보는 '{CAUSE_KO[j.choice]}'입니다(판단 모델 미연결, 확률 없음) {cite}.")
    return "\n".join([text, sentence, "이는 상관에 기반한 후보이며 인과를 뜻하지 않습니다."])


def _scan(s: Slots, tb: Toolbox, method, threshold) -> tuple[str, dict]:
    call = _Calls(tb)
    start, end = (s.date, s.date) if s.date is not None else (s.start, s.end)
    if s.emd:
        call("detect_anomalies", {"signal": s.signal, "emd": s.emd, "start": _d(start), "end": _d(end), "method": method, "threshold": threshold})
        return template_text(call.results), call.results
    rid, r = call("scan_regions", {"signal": s.signal, "start": _d(start), "end": _d(end), "method": method, "threshold": threshold})
    d = r.data
    period = f"{d['start']}~{d['end']}" if d["start"] else "수집된 전체 기간"
    if not d["with_anomalies"]:
        return f"{s.signal} 기준 {period} 동안 {d['checked']}개 읍면동에서 기준을 넘는 이상 구간은 없었습니다 [{rid}].", call.results
    lines = [f"{s.signal} 기준 {period} 동안 {d['checked']}개 읍면동 중 {d['with_anomalies']}곳에서 이상 구간 {d['episode_count']}개가 "
             f"확인됐습니다(평소 변동폭 대비 점수가 큰 순) [{rid}]."]
    for e in d["episodes"][:5]:
        span = e["start"] if e["start"] == e["end"] else f"{e['start']}~{e['end']}"
        word = "많음" if e["direction"] == "up" else "적음"
        lines.append(f"- {e['emd']} {span}({e['kind']}): 가장 큰 날 {e['peak_date']} 기대 대비 {abs(e['peak_pct'])}% {word}, 점수 {e['peak_score']} [{rid}].")
    lines.append("이유가 궁금한 구간은 '읍면동 + 날짜 + 왜'로 물어보세요.")
    return "\n".join(lines), call.results


def _nobreak(text: str) -> str:
    """검증기는 문장 단위로 근거를 확인하므로, 인용한 제목·원문 안에서 문장이 끊기지 않게 마침표를 바꾼다."""
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"(?<=\d)[.](?=\s)", "", t)          # '3. 반출' 같은 번호 → '3 반출'
    return re.sub(r"[.!?。](?=\s)", " /", t).rstrip(".!?。")


def _snippet(text: str, n: int = 160) -> str:
    t = re.sub(r"\|?\s*:?-{3,}:?\s*(?=\|)", " ", text)       # 마크다운 표 구분선
    t = re.sub(r"\s*\|\s*", " · ", t.replace("**", ""))
    t = re.sub(r"(\s·)+", " ·", re.sub(r"\s+", " ", t)).strip(" ·")
    if len(t) > n:
        t = t[:n].rsplit(" ", 1)[0] + "…"
    return _nobreak(t)


def _docs(q, tb: Toolbox) -> tuple[str, dict]:
    call = _Calls(tb)
    rid, r = call("search_docs", {"query": q, "k": 3})
    ps = r.data["passages"]
    if not ps:
        return "관련 문서를 찾지 못했습니다. 다른 표현으로 물어봐 주세요.", call.results
    lines = [f"관련 문서를 찾았습니다(원문 일부, 출처 포함) [{rid}]."]
    lines += [f"- {_nobreak(p['title'])} ({_nobreak(p['locator'])}): {_snippet(p['text'])} [{rid}]" for p in ps]
    return "\n".join(lines), call.results


def answer(q: str, tb: Toolbox, http=requests, judge=judge_cause, method: str = "seasonal_z", threshold: float = 3.5) -> LocalRun:
    intent, prob, router = route(q, http=http)
    lo, hi = _data_range(tb.store)
    s = parse_slots(q, lo, hi)
    try:
        if s.bad_date and intent in ("explain", "scan"):
            text, results = BAD_DATE, {}
        elif intent == "explain":
            text, results = _explain(q, s, tb, judge, method, threshold)
        elif intent == "scan":
            text, results = _scan(s, tb, method, threshold)
        elif intent == "docs":
            text, results = _docs(q, tb)
        else:
            text, results = SCOPE_TEXT, {}
    except ToolError as e:
        text, results = f"요청한 지역·신호의 데이터가 아직 없습니다({e}).", {}
    v = verify(text, results)
    return LocalRun(q, [], results=results, final_text=text if v.ok else WITHHELD, verified=v.ok,
                    verify_errors=v.errors, verify_warnings=v.warnings, intent=intent, intent_prob=prob, router=router, slots=s)
