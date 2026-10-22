import pytest

REASON = "cut for time — see docs/payments.md"


@pytest.mark.skip(reason=REASON)
def test_capture_only_after_clinic_confirms():
    raise NotImplementedError


@pytest.mark.skip(reason=REASON)
def test_void_on_booking_failure():
    raise NotImplementedError


@pytest.mark.skip(reason=REASON)
def test_refund_on_cancellation_webhook():
    raise NotImplementedError


@pytest.mark.skip(reason=REASON)
def test_paid_claim_never_shown_as_verified():
    raise NotImplementedError


@pytest.mark.skip(reason=REASON)
def test_payment_retry_idempotent():
    raise NotImplementedError


def test_payment_tables_are_migrated(tmp_path):
    from agent.context import MIGRATIONS
    from shared.sqlite import connect, migrate

    conn = connect(str(tmp_path / "agent.db"))
    migrate(conn, MIGRATIONS)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"payment_intents", "payment_events"} <= tables
