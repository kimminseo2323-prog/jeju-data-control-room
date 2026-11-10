"""도구 호출 루프. LLM은 step(messages, tools) -> LLMReply 인터페이스만 지키면 공급자와 무관하게 동작한다."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agent.tools import ToolError, ToolResult, Toolbox

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


def run_agent(question: str, llm, toolbox: Toolbox, max_steps: int = 8, history: list[dict] | None = None) -> AgentRun:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *(history or []), {"role": "user", "content": question}]
    run = AgentRun(question, messages)
    while True:
        reply: LLMReply = llm.step(messages, toolbox.specs())
        if not reply.tool_calls:
            run.final_text = reply.text or ""
            messages.append({"role": "assistant", "content": run.final_text})
            return run
        messages.append({"role": "assistant", "content": reply.text or "",
                         "tool_calls": [{"id": c.id, "name": c.name, "args": c.args} for c in reply.tool_calls]})
        for call in reply.tool_calls:
            if len(run.calls) >= max_steps:
                run.stopped = True
                run.final_text = reply.text or "도구 호출 한도에 도달해 분석을 중단했습니다."
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
