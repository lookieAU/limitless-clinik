from agent.pipeline.verify_reply import repeats_system_lines
from tests.scenarios.scripts import call, claim

OFFER = "Dr Bela Nair has Mon 2 Nov, 9:30 am IST free (checked just now). Shall I book it for you? Nothing changes until you say yes."


def test_restating_the_offer_counts_as_repeat():
    assert repeats_system_lines("Dr Bela Nair has openings today, and the earliest is 9:30 am IST. Would you like it?", OFFER)
    assert repeats_system_lines("Your reference is ca-1003.", "Done — ref CA-1003 (checked just now).")


def test_new_information_is_not_a_repeat():
    assert not repeats_system_lines("11:00 is taken, so here's the closest option.", OFFER)
    assert not repeats_system_lines("Anything else?", "Done — Dr Arjun Mehta, Thu 5 Nov, 3:00 pm IST is confirmed by the clinic, ref CA-1003.")


def test_second_question_next_to_an_offer_is_a_repeat():
    assert repeats_system_lines("Anything else?", OFFER)


async def test_turn_drops_prose_that_repeats_the_offer(make_harness):
    text = "Something with Dr B today?"
    script = {
        text: {
            "extract": {"intent": "book", "claims": [claim("doctor", "dr_b", "Dr B")]},
            "steps": [
                call("check_availability", doctor_id="dr_b", date_from="2026-11-02", time_from="09:30", time_to="09:30"),
                call("propose_slot", slot_id="dr_b_20261102_0930"),
                {"text": "Dr Bela Nair has openings today, and the earliest is 9:30 am IST. Would you like me to book it?"},
            ],
        }
    }
    harness = await make_harness(script)
    result = await harness.say(text)
    assert result["reply"].count("9:30 am") == 1 and result["reply"].count("?") == 1
    assert harness.events("prose_dropped")


def test_rephrased_offer_without_time_is_still_a_repeat():
    assert repeats_system_lines("Yes, Dr Bela Nair has openings today. Just say yes if you'd like the first one.", OFFER)
    assert repeats_system_lines("Friday morning works. Just say yes if that suits you.", OFFER)
