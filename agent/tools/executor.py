from agent.llm.types import ToolCall
from agent.pipeline.policy_gate import CLINIC_ERRORS, SEGMENT_CODES, Refusal
from agent.pipeline.state import TurnState
from agent.tools import reads, writes

HANDLERS = {
    "check_availability": reads.check_availability,
    "propose_slot": reads.propose_slot,
    "get_booking": reads.get_booking,
    "recall": reads.recall_tool,
    "book": writes.book,
    "reschedule": writes.reschedule,
    "cancel": writes.cancel,
}


async def execute_tool(state: TurnState, call: ToolCall) -> dict:
    handler = HANDLERS.get(call.name)
    state.log("tool_call", {"name": call.name, "args": call.args})
    if handler is None:
        return {"ok": False, "error": "unknown_tool"}
    try:
        result = await handler(state, call.args)
    except Refusal as refusal:
        state.log("gate_refused", {"tool": call.name, "code": refusal.code, "detail": refusal.detail})
        if refusal.code in SEGMENT_CODES:
            state.add("refusal", f"refusal.{refusal.code}", **refusal.params)
        if refusal.code == "clinic_error":
            state.add("refusal", "refusal.clinic_error", **refusal.params)
        result = {"ok": False, "refused": refusal.code, "detail": refusal.detail}
    except CLINIC_ERRORS as error:
        state.log("clinic_unreachable", {"tool": call.name, "error": str(error)})
        result = {"ok": False, "error": "clinic_unreachable"}
    except (KeyError, ValueError, TypeError) as error:
        result = {"ok": False, "error": "bad_arguments", "detail": str(error)}
    state.log("tool_result", {"name": call.name, "ok": result.get("ok", False)})
    return result
