"""도구 호출 루프. LLM은 step(messages, tools) -> LLMReply 인터페이스만 지키면 공급자와 무관하게 동작한다."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agent.tools import ToolError, ToolResult, Toolbox
from app.agent.verify import verify

SYSTEM_PROMPT = """너는 제주 관광·교통 데이터 관제실의 분석 Agent다.
- 숫자는 반드시 도구 결과에서만 가져오고, 문장 끝에 근거 결과 id를 [R1]처럼 붙인다.
- 원인은 단정하지 말고 '원인 후보'와 근거, 확신도(상·중·하)로 말한다.
- 데이터가 없는 기간·지역·실시간 정보는 없다고 말하고 가능한 대안을 제시한다.
- 데이터 출처·정의 질문은 search_docs로 확인한 뒤 출처와 함께 답한다."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMReply:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class AgentRun:
    question: str
    messages: list[dict]
    calls: list[ToolCall] = field(default_factory=list)
    results: dict[str, ToolResult] = field(default_factory=dict)
    final_text: str = ""
    stopped: bool = False
    verified: bool = False
    revisions: int = 0
    verify_errors: list[str] = field(default_factory=list)
    verify_warnings: list[str] = field(default_factory=list)

WITHHELD = ("답변 문장이 검증을 통과하지 못해 표시하지 않습니다. "
            "아래 계산 결과 표와 차트를 확인해 주세요.")


def run_agent(question: str, llm, toolbox: Toolbox, max_steps: int = 8, history: list[dict] | None = None,
              max_revisions: int = 2) -> AgentRun:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *(history or []), {"role": "user", "content": question}]
    run = AgentRun(question, messages)
    while True:
        reply: LLMReply = llm.step(messages, toolbox.specs())
        if not reply.tool_calls:
            text = reply.text or ""
            messages.append({"role": "assistant", "content": text})
            v = verify(text, run.results)
            run.verify_errors, run.verify_warnings = v.errors, v.warnings
            if v.ok:
                run.final_text, run.verified = text, True
                return run
            if run.revisions >= max_revisions:
                run.final_text, run.verified = WITHHELD, False
                return run
            run.revisions += 1
            messages.append({"role": "user", "content": "검증 실패 — 아래 문제를 고쳐 다시 작성하세요. 숫자는 도구 결과에 있는 값만 쓰고 "
                             "문장마다 [Rn] 근거를 붙이세요.\n- " + "\n- ".join(v.errors)})
            continue
        messages.append({"role": "assistant", "content": reply.text or "",
                         "tool_calls": [{"id": c.id, "name": c.name, "args": c.args} for c in reply.tool_calls]})
        for call in reply.tool_calls:
            if len(run.calls) >= max_steps:
                run.stopped = True
                run.final_text = "도구 호출 한도에 도달해 분석을 중단했습니다. 검증된 답변이 없어 문장은 표시하지 않습니다."   # 중간 문장은 검증 전이라 보이지 않음
                return run
            run.calls.append(call)
            rid = f"R{len(run.results) + 1}"
            try:
                res = toolbox.dispatch(call.name, call.args, rid)
                run.results[rid] = res
                content = res.for_llm()
            except ToolError as e:
                content = json.dumps({"error": str(e)}, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": content})
