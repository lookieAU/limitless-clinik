from agent.memory.validate_summary import validate_summary


def structured(*constraints, snapshot=()):
    return {"constraints": list(constraints), "clinic_snapshot": list(snapshot)}


NOT_THU = {"subject": "day", "value": "thu", "polarity": "negative", "claim_ids": ["c1"]}
NOT_THIS_WEEK = {"subject": "week", "value": "this_week", "polarity": "negative", "claim_ids": ["c2"]}


def test_negated_value_passes():
    assert validate_summary(structured(NOT_THU), "Customer said: not Thursday.").ok


def test_bare_positive_fails():
    result = validate_summary(structured(NOT_THU), "Customer prefers Thursday.")
    assert not result.ok and result.errors[0].startswith("negation lost: day=thu")


def test_missing_constraint_fails():
    assert validate_summary(structured(NOT_THU), "Customer wants an appointment.").errors[0].startswith("negation dropped")


def test_one_negated_and_one_bare_mention_fails():
    assert not validate_summary(structured(NOT_THU), "Not Thursday. Book Thursday afternoon.").ok


def test_hindi_postposition_negation_passes():
    assert validate_summary(structured(NOT_THU), "ग्राहक ने कहा: गुरुवार नहीं।").ok
    assert validate_summary(structured(NOT_THIS_WEEK), "ग्राहक: इस हफ्ते नहीं।").ok


def test_romanized_hindi_negation_passes():
    assert validate_summary(structured(NOT_THU), "guruvar nahi chalega").ok


def test_hindi_bare_mention_fails():
    assert not validate_summary(structured(NOT_THU), "ग्राहक को गुरुवार पसंद है।").ok


def test_clinic_status_needs_as_of():
    snap = [{"booking_id": "b1", "ref": "CA-1003", "status": "cancelled", "observed_utc": "2026-11-02T04:00:00Z"}]
    assert not validate_summary(structured(snapshot=snap), "CA-1003 is cancelled.").ok
    assert validate_summary(structured(snapshot=snap), "CA-1003 cancelled as of 2026-11-02T04:00:00Z.").ok
