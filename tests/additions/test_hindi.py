from datetime import date

from agent.memory.load import load_memory
from agent.memory.summarize import summarize
from tests.fixtures.lossy_summarizer import LossySummarizer
from tests.scenarios.scripts import THU_1500, call, claim
from tests.scenarios.test_s06_negation_summary import seed_claim

RAVI_BOOK = "Thursday 3 baje Dr A ke saath book kar do"
HINGLISH_MOVE = "Next week kar do… Thursday 3 baje chalega"
SCRIPT = {
    RAVI_BOOK: {
        "extract": {"intent": "book", "claims": [claim("day", "thu", "Thursday"), claim("time_window", "15:00", "3 baje"), claim("doctor", "dr_a", "Dr A")]},
        "steps": [call("check_availability", doctor_id="dr_a", date_from="2026-11-05"), call("book", slot_id=THU_1500), {"text": "और कुछ?"}],
    },
    "कन्फर्म हुआ?": {"extract": {"intent": "status_query"}, "steps": [{"text": "क्लिनिक से ताज़ा जानकारी यह है।"}]},
    HINGLISH_MOVE: {
        "extract": {"intent": "reschedule", "claims": [claim("week", "next_week", "Next week"), claim("day", "thu", "Thursday"), claim("time_window", "15:00", "3 baje")]},
        "steps": [call("reschedule", slot_id="dr_a_20261112_1500")],
    },
}


async def test_hindi_negation_survives_summary(make_harness):
    harness = await make_harness()
    seed_claim(harness, "u_ravi", "day", "thu", "negative", "गुरुवार नहीं", lang="hi")
    good = await summarize(harness.agent_ctx, "u_ravi", date(2026, 11, 2))
    assert good.validated and "गुरुवार नहीं" in good.prose
    bad = await summarize(harness.agent_ctx, "u_ravi", date(2026, 11, 2), llm=LossySummarizer())
    assert not bad.validated
    assert load_memory(harness.agent_ctx.conn, "u_ravi").summary_id == good.id


async def test_hindi_did_you_confirm_rechecks(make_harness):
    harness = await make_harness(SCRIPT)
    await harness.say(RAVI_BOOK, user_id="u_ravi")
    await harness.admin(f"slots/{THU_1500}/cancel")
    result = await harness.say("कन्फर्म हुआ?", user_id="u_ravi")
    assert result["lang"] == "hi"
    assert "clinic_read" in result["events"]
    assert "कन्फर्म" not in result["reply"] and "confirmed" not in result["reply"].lower()
    assert "रद्द" in result["reply"]


async def test_hinglish_contradiction_asks_one_question(make_harness):
    harness = await make_harness(SCRIPT)
    await harness.say(RAVI_BOOK, user_id="u_ravi")
    writes = harness.clinic_writes()
    result = await harness.say(HINGLISH_MOVE, user_id="u_ravi")
    assert result["lang"] == "hi"
    assert harness.clinic_writes() == writes
    assert result["reply"].count("?") == 1 and "12 Nov" in result["reply"] and "5 Nov" in result["reply"]
    assert "अगले हफ्ते" in result["reply"]
