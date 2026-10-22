THU_1500 = "dr_a_20261105_1500"
FRI_0900 = "dr_a_20261106_0900"
FRI_1100 = "dr_a_20261106_1100"
THU2_1500 = "dr_a_20261112_1500"


def claim(subject: str, value: str, raw: str, polarity: str = "positive") -> dict:
    return {"subject": subject, "value": value, "raw_span": raw, "polarity": polarity}


def call(name: str, **args) -> dict:
    return {"tool_calls": [{"name": name, "args": args}]}


BOOK_THU = {
    "Book me Thursday 3pm with Dr A.": {
        "extract": {
            "intent": "book",
            "claims": [claim("day", "thu", "Thursday"), claim("time_window", "15:00", "3pm"), claim("doctor", "dr_a", "Dr A")],
        },
        "steps": [
            call("check_availability", doctor_id="dr_a", date_from="2026-11-05", time_from="15:00", time_to="15:30"),
            call("book", slot_id=THU_1500),
            {"text": "Anything else I can help with?"},
        ],
    }
}

MOVE_FRI = {
    "Actually make it Friday before noon.": {
        "extract": {"intent": "reschedule", "claims": [claim("day", "fri", "Friday"), claim("time_window", "before_12:00", "before noon")]},
        "steps": [
            call("check_availability", doctor_id="dr_a", date_from="2026-11-06", time_from="09:00", time_to="12:00"),
            call("book", slot_id=FRI_0900),
            call("propose_slot", slot_id=FRI_0900, action="reschedule"),
            {"text": "11:00 is taken, so here's the closest option."},
        ],
    },
    "Yes": {
        "extract": {"intent": "accept_offer"},
        "steps": [call("reschedule", slot_id=FRI_0900), {"text": "All done on my side."}],
    },
}

NEXT_WEEK_THEN_THURSDAY = {
    "Can you move it to next week?": {
        "extract": {"intent": "reschedule", "claims": [claim("week", "next_week", "next week")]},
        "steps": [{"text": "Sure — which day works for you?"}],
    },
    "Thursday is fine.": {
        "extract": {"intent": "reschedule", "claims": [claim("day", "thu", "Thursday")]},
        "steps": [call("reschedule", slot_id=THU2_1500), {"text": "Moving it now."}],
    },
}

STATUS_QUESTION = {
    "Hi — did you confirm my booking?": {
        "extract": {"intent": "status_query"},
        "steps": [{"text": "Here's what the clinic says right now."}],
    }
}
