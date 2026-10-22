from demo.replay import build_replay


async def test_full_replay_runs_cleanly(tmp_path):
    replay = await build_replay(tmp_path)
    steps = []
    while not replay.done:
        steps.append(await replay.next())
    harness = replay.harness
    try:
        book, window, yes, hinglish, answer, cancel, next_day, summary, lossy = steps
        assert "CA-1003" in book.reply and "confirmed by the clinic" in book.reply
        assert "Nothing changes until you say yes" in window.reply
        assert "Fri 6 Nov, 9:00 am IST is confirmed by the clinic" in yes.reply
        assert hinglish.result["session_state"] == "awaiting_clarification" and hinglish.reply.count("?") == 1
        assert "Thu 12 Nov, 3:00 pm IST" in answer.reply
        assert "webhooks delivered: 1" in cancel.notes[0]
        assert next_day.reply.startswith("First, an update from the clinic")
        assert "confirmed" not in next_day.reply.lower() and "I can rebook you" in next_day.reply
        assert "Mon 9 Nov" in next_day.reply and "Thu 5 Nov" not in next_day.reply
        assert summary.notes[0].startswith("summary KEPT") and "not this week" in summary.notes[0]
        assert lossy.notes[0].startswith("summary REJECTED")
        assert len(harness.clinic_bookings()) == 1
        live = {(c["subject"], c["value"], c["polarity"]) for c in (await harness.state())["claims"] if c["status"] in ("active", "clarified")}
        assert ("week", "this_week", "negative") in live
        assert ("time_window", "before_12:00", "positive") not in live
    finally:
        await harness.close()
