import json

from agent.llm.types import AssistantStep, PlanMessage, PlanRequest
from agent.pipeline.prompt import system_prompt
from agent.pipeline.state import TurnState
from agent.repo import messages
from agent.tools.executor import execute_tool
from agent.tools.reads import offer_segments
from agent.tools.specs import TOOL_SPECS

MAX_STEPS = 6
REWRITE_SYSTEM = (
    "Rewrite the clinic assistant message you are given so it makes no claim about whether any booking is confirmed, "
    "booked, scheduled, set or cancelled. Keep any question or offer of help. Same language, at most two sentences. "
    "Output only the rewritten message."
)


HISTORY_TURNS = 6


def assistant_turn(result: dict) -> str:
    parts = []
    if result.get("system_text"):
        parts.append(f"[Shown by the system, not written by you: {result['system_text']}]")
    if result.get("prose"):
        parts.append(result["prose"])
    return "\n".join(parts) or "[no reply text]"


def history(state: TurnState) -> list[PlanMessage]:
    turns = []
    for row in messages.transcript(state.conn, state.session_id)[-2 * HISTORY_TURNS - 1 :]:
        if row["role"] != "customer":
            continue
        turns.append(PlanMessage(role="user", text=row["text"]))
        if row["result_json"]:
            turns.append(PlanMessage(role="assistant", text=assistant_turn(json.loads(row["result_json"]))))
    return turns


async def safe_step(state: TurnState, request: PlanRequest) -> AssistantStep:
    try:
        return await state.ctx.llm.step(request)
    except Exception as error:
        state.log("llm_failed", {"error": str(error)[:300]})
        return AssistantStep()


async def plan(state: TurnState) -> None:
    system = await system_prompt(state)
    conversation = history(state)
    for step_index in range(MAX_STEPS):
        step = await safe_step(state, PlanRequest(turn_key=state.message_id, system=system, messages=conversation, tools=TOOL_SPECS))
        if not step.tool_calls:
            state.prose = step.text
            break
        calls = [call.model_copy(update={"id": call.id or f"call_{step_index}_{i}"}) for i, call in enumerate(step.tool_calls)]
        conversation.append(PlanMessage(role="assistant", text=step.text, tool_calls=calls, raw=step.raw))
        for call in calls:
            result = await execute_tool(state, call)
            conversation.append(PlanMessage(role="tool", tool_call_id=call.id, text=json.dumps(result, default=str)))
    offer_segments(state)
    state.plan_messages = [system, conversation]


async def regenerate(state: TurnState) -> str:
    if not state.plan_messages:
        return ""
    request = PlanRequest(
        turn_key=state.message_id, system=REWRITE_SYSTEM, messages=[PlanMessage(role="user", text=state.prose)], tools=[], allow_tools=False
    )
    return (await safe_step(state, request)).text
