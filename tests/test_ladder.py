"""Run with: python -m pytest tests  (or just: python tests/test_ladder.py)"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from ladder import AT_RISK, DONE, OFF_TRACK, ON_TRACK, decide, rate  # noqa: E402

D = date(2026, 10, 19)


def row(**kw):
    base = dict(start_date="2026-09-01", due_date="2026-12-31", progress_pct=40,
                last_update="2026-10-18", open_blockers=0)
    return {**base, **kw}


def test_status_rules():
    assert rate(row(), D)[0] == ON_TRACK
    assert rate(row(open_blockers=1), D)[0] == AT_RISK
    assert rate(row(open_blockers=2), D)[0] == OFF_TRACK
    assert rate(row(last_update="2026-09-20"), D)[0] == OFF_TRACK
    assert rate(row(due_date="2026-10-10", progress_pct=90), D)[0] == OFF_TRACK
    assert rate(row(progress_pct=100), D)[0] == DONE


def test_ladder_waits_14_days_between_steps():
    d, h = decide("X", OFF_TRACK, None, D)
    assert (d.this_week, h.step) == ("New step 1", 1)
    d, h = decide("X", OFF_TRACK, h, D + timedelta(days=7))
    assert (d.this_week, h.step) == ("Reminder", 1)
    d, h = decide("X", OFF_TRACK, h, D + timedelta(days=14))
    assert (d.this_week, h.step) == ("New step 2", 2)


def test_no_step_four():
    _, h = decide("X", OFF_TRACK, None, D)
    for i in range(1, 6):
        d, h = decide("X", OFF_TRACK, h, D + timedelta(days=14 * i))
    assert h.step == 3 and d.this_week == "Back on exec agenda"


def test_reset_after_four_clean_weeks():
    _, h = decide("X", OFF_TRACK, None, D)
    d, h = decide("X", ON_TRACK, h, D + timedelta(days=28))
    assert h.step == 0 and d.this_week == "Reset"


def test_at_risk_never_climbs():
    _, h = decide("X", AT_RISK, None, D)
    assert h.step == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all tests pass")
