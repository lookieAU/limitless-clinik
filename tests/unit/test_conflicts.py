from datetime import date

from agent.pipeline.conflicts import ClaimView, apply_claims, candidate_dates, option_matches

TODAY = date(2026, 11, 2)


def c(seq: int, subject: str, value: str, polarity: str = "positive") -> ClaimView:
    return ClaimView(f"c{seq}", subject, value, polarity, seq)


def test_day_alone_means_next_occurrence():
    assert candidate_dates([c(1, "day", "thu")], TODAY) == [date(2026, 11, 5)]


def test_week_then_day_is_ambiguous_with_concrete_dates():
    outcome = apply_claims([c(1, "week", "next_week")], [c(2, "day", "thu")], TODAY)
    assert outcome.conflict.kind == "ambiguous"
    assert [o.day for o in outcome.conflict.options] == [date(2026, 11, 12), date(2026, 11, 5)]


def test_same_subject_change_supersedes_without_question():
    outcome = apply_claims([c(1, "day", "thu"), c(2, "time_window", "15:00")], [c(3, "day", "fri"), c(4, "time_window", "before_12:00")], TODAY)
    assert outcome.conflict is None
    assert outcome.superseded == [("c1", "c3"), ("c2", "c4")]


def test_positive_after_negative_is_contradiction():
    outcome = apply_claims([c(1, "day", "thu", "negative")], [c(2, "day", "thu")], TODAY)
    assert outcome.conflict.kind == "contradiction"


def test_negative_week_excludes_dates():
    assert candidate_dates([c(1, "week", "this_week", "negative"), c(2, "day", "thu")], TODAY) == [date(2026, 11, 12)]


def test_date_contradicting_negative_day_is_contradiction():
    outcome = apply_claims([c(1, "day", "thu", "negative")], [c(2, "date", "2026-11-12")], TODAY)
    assert outcome.conflict.kind == "contradiction"


def test_answer_picks_next_week_option():
    outcome = apply_claims([c(1, "week", "next_week")], [c(2, "day", "thu")], TODAY)
    answer = [c(3, "week", "next_week"), c(4, "week", "this_week", "negative")]
    matches = [o.key for o in outcome.conflict.options if option_matches(o, answer, TODAY)]
    assert matches == ["with_week"]


def test_detect_false_never_raises_conflict():
    outcome = apply_claims([c(1, "week", "next_week")], [c(2, "day", "thu")], TODAY, detect=False)
    assert outcome.conflict is None
