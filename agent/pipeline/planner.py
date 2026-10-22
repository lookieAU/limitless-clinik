import json

from agent.llm.types import PlanMessage, PlanRequest
from agent.pipeline.prompt import system_prompt
from agent.pipeline.state import TurnState
from agent.repo import messages
from agent.tools.executor import execute_tool
from agent.tools.reads import offer_segments
from agent.tools.specs import TOOL_SPECS

MAX_STEPS = 6
REWRITE_NOTE = (
    "SYSTEM CHECK: your reply mentioned booking status in your own words, which is not allowed. The verified status "
    "lines are shown separately. Rewrite your reply in at most two sentences without any status words."
)


def history(state: TurnState) -> list[PlanMessage]:
    rows = messages.recent(state.conn, state.session_id, 8)
    return [PlanMessage(role="user" if row["role"] == "customer" else "assistant", text=row["text"]) for row in rows]


async def plan(state: TurnState) -> None:
    system = await system_prompt(state)
    conversation = history(state)
    for step_index in range(MAX_STEPS):
        step = await state.ctx.llm.step(
            PlanRequest(turn_key=state.message_id, system=system, messages=conversation, tools=TOOL_SPECS)
        )
        if not step.tool_calls:
            state.prose = step.text
            break
        calls = [call.model_copy(update={"id": call.id or f"call_{step_index}_{i}"}) for i, call in enumerate(step.tool_calls)]
        conversation.append(PlanMessage(role="assistant", text=step.text, tool_calls=calls))
        for call in calls:
            result = await execute_tool(state, call)
            conversation.append(PlanMessage(role="tool", tool_call_id=call.id, text=json.dumps(result, default=str)))
    offer_segments(state)
    state.plan_messages = [system, conversation]


async def regenerate(state: TurnState) -> str:
    if not state.plan_messages:
        return ""
    system, conversation = state.plan_messages
    retry = conversation + [PlanMessage(role="assistant", text=state.prose), PlanMessage(role="user", text=REWRITE_NOTE)]
    step = await state.ctx.llm.step(PlanRequest(turn_key=state.message_id, system=system, messages=retry, tools=TOOL_SPECS, allow_tools=False))
    return step.text
