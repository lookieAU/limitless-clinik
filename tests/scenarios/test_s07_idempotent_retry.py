from shared.ids import idempotency_key
from tests.scenarios.scripts import BOOK_THU, THU_1500


async def test_same_chat_request_twice_books_once(make_harness):
    harness = await make_harness(BOOK_THU)
    first = await harness.say("Book me Thursday 3pm with Dr A.", client_msg_id="retry-1")
    second = await harness.say("Book me Thursday 3pm with Dr A.", client_msg_id="retry-1")
    assert first == second
    assert len(harness.clinic_bookings()) == 1


async def test_same_clinic_write_twice_returns_first_result(make_harness):
    harness = await make_harness()
    adapter = harness.agent_ctx.registry.get("clinic_a")
    key = idempotency_key("u_asha", "book", THU_1500, "intent-1")
    first = await adapter.book("c_asha", THU_1500, key)
    second = await adapter.book("c_asha", THU_1500, key)
    assert first == second
    assert len(harness.clinic_bookings()) == 1
