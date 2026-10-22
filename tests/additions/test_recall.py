from agent.memory.recall import recall
from agent.repo import claims
from tests.scenarios.test_s06_negation_summary import seed_claim


async def test_recall_keeps_negation(make_harness):
    harness = await make_harness()
    seed_claim(harness, "u_asha", "day", "thu", "negative", "not Thursday")
    seed_claim(harness, "u_asha", "doctor", "dr_b", "positive", "Dr B")
    hits = recall(harness.agent_ctx, "u_asha", "Thursday", k=3)
    assert hits[0]["subject"] == "day" and hits[0]["polarity"] == "negative"
    assert hits[0]["said"] == "not Thursday"


async def test_recall_is_multilingual(make_harness):
    harness = await make_harness()
    seed_claim(harness, "u_asha", "day", "thu", "negative", "not Thursday")
    assert recall(harness.agent_ctx, "u_asha", "गुरुवार", k=1)[0]["polarity"] == "negative"


async def test_superseded_claims_are_excluded(make_harness):
    harness = await make_harness()
    old = seed_claim(harness, "u_asha", "day", "thu", "positive", "Thursday")
    new = seed_claim(harness, "u_asha", "day", "fri", "positive", "Friday")
    claims.supersede(harness.agent_ctx.conn, old["id"], new["id"])
    values = [hit["value"] for hit in recall(harness.agent_ctx, "u_asha", "Thursday Friday", k=5)]
    assert "thu" not in values and "fri" in values
