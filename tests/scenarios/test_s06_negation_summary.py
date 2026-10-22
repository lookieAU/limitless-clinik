from datetime import date

from agent.memory.load import load_memory
from agent.memory.summarize import summarize
from agent.memory.validate_summary import validate_summary
from agent.repo import claims, sessions, users
from tests.fixtures.lossy_summarizer import LossySummarizer

DAY = date(2026, 11, 2)


def seed_claim(harness, user_id: str, subject: str, value: str, polarity: str, raw: str, lang: str = "en") -> dict:
    ctx = harness.agent_ctx
    user = users.get_user(ctx.conn, user_id)
    session = sessions.create_session(ctx.conn, user, ctx.clock.now())
    draft = {"kind": "constraint", "subject": subject, "value": value, "polarity": polarity, "raw_span": raw}
    return claims.insert_claim(ctx.conn, user_id, session["id"], "msg_seed", draft, lang, ctx.clock.now())


async def test_negation_survives_summary(make_harness):
    harness = await make_harness()
    seed_claim(harness, "u_asha", "day", "thu", "negative", "not Thursday")
    summary = await summarize(harness.agent_ctx, "c_asha", DAY)
    assert {"subject": "day", "value": "thu", "polarity": "negative"}.items() <= summary.structured["constraints"][0].items()
    assert validate_summary(summary.structured, summary.prose).ok
    assert summary.validated and "not Thursday" in summary.prose
    assert load_memory(harness.agent_ctx.conn, "u_asha").summary_id == summary.id


async def test_lossy_summarizer_is_rejected(make_harness):
    harness = await make_harness()
    seed_claim(harness, "u_asha", "day", "thu", "negative", "not Thursday")
    good = await summarize(harness.agent_ctx, "c_asha", DAY)
    bad = await summarize(harness.agent_ctx, "c_asha", DAY, llm=LossySummarizer())
    verdict = validate_summary(bad.structured, bad.prose)
    assert not verdict.ok and "negation lost: day=thu" in verdict.errors[0]
    assert not bad.validated
    assert load_memory(harness.agent_ctx.conn, "u_asha").summary_id == good.id
    assert harness.events("summary_rejected")
