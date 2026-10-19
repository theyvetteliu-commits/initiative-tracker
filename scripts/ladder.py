"""Status rules and the escalation ladder.

Pure functions, no file or network access, so the rules can be tested on
their own (see tests/test_ladder.py).

Status (worked out fresh every week):
- Off track: past due and not done, OR progress 25+ points behind plan,
  OR no update for 21+ days, OR 2+ open blockers.
- At risk:   progress 10-25 points behind plan, OR no update for 10+ days,
  OR 1 open blocker, OR due within 14 days and under 80% done.
- On track:  none of the above.
- Done:      100% complete. Done projects leave the ladder.

Escalation ladder (only off-track projects climb it):
- Step 1  Nudge the owner: what's slipping, and a recovery plan by Friday.
- Step 2  Flag to the lead: owner and lead review it together this week.
- Step 3  Exec review: added to the exec agenda with a decision needed
          (re-scope, re-resource or re-date).
- A project only climbs to the next step if it is still off track
  14+ days after its last step. In between it gets a weekly reminder.
  That gives the owner a real chance to recover before it goes up.
- There is no step 4. Still off track after step 3 = back on the exec
  agenda every 2 weeks until it is fixed or formally re-dated.
- At risk = a heads-up to the owner, no step.
- The ladder resets after 4 weeks with no off-track week.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ON_TRACK, AT_RISK, OFF_TRACK, DONE = "On track", "At risk", "Off track", "Done"

STEP_GAP_DAYS = 14
RESET_DAYS = 28

STEP_ACTION = {
    1: "Nudge owner: recovery plan by Friday",
    2: "Flag to lead: review with owner this week",
    3: "Exec review: decide re-scope, re-resource or re-date",
}

HISTORY_FIELDS = ["initiative_id", "step", "last_step_date", "last_off_track_date", "updated_on"]


# ---------- status ----------

def planned_pct(start: date, due: date, today: date) -> float:
    """Where the project should be by now, if work were spread evenly."""
    if today <= start:
        return 0.0
    if today >= due:
        return 100.0
    return 100.0 * (today - start).days / (due - start).days


def rate(p: dict, today: date) -> tuple[str, list[str]]:
    """Return (status, reasons) for one initiative row."""
    progress = float(p["progress_pct"])
    if progress >= 100:
        return DONE, []
    start, due = date.fromisoformat(p["start_date"]), date.fromisoformat(p["due_date"])
    gap = planned_pct(start, due, today) - progress
    stale = (today - date.fromisoformat(p["last_update"])).days
    blockers = int(p["open_blockers"] or 0)
    days_left = (due - today).days

    off, risk = [], []
    if days_left < 0:
        off.append(f"{-days_left} days past due")
    if gap >= 25:
        off.append(f"{gap:.0f} pts behind plan")
    elif gap >= 10:
        risk.append(f"{gap:.0f} pts behind plan")
    if stale >= 21:
        off.append(f"no update for {stale} days")
    elif stale >= 10:
        risk.append(f"no update for {stale} days")
    if blockers >= 2:
        off.append(f"{blockers} open blockers")
    elif blockers == 1:
        risk.append("1 open blocker")
    if 0 <= days_left <= 14 and progress < 80:
        risk.append(f"due in {days_left} days at {progress:.0f}%")

    if off:
        return OFF_TRACK, off + risk
    if risk:
        return AT_RISK, risk
    return ON_TRACK, []


# ---------- ladder ----------

@dataclass
class History:
    initiative_id: str
    step: int = 0
    last_step_date: date | None = None
    last_off_track_date: date | None = None
    updated_on: date | None = None

    @classmethod
    def from_row(cls, row: dict) -> "History":
        d = lambda v: date.fromisoformat(v) if v else None  # noqa: E731
        return cls(row["initiative_id"], int(row.get("step") or 0),
                   d(row.get("last_step_date")), d(row.get("last_off_track_date")), d(row.get("updated_on")))

    def to_row(self) -> dict:
        s = lambda v: v.isoformat() if v else ""  # noqa: E731
        return {"initiative_id": self.initiative_id, "step": self.step,
                "last_step_date": s(self.last_step_date),
                "last_off_track_date": s(self.last_off_track_date), "updated_on": s(self.updated_on)}


@dataclass
class Decision:
    initiative_id: str
    status: str
    step_before: int
    step_after: int
    this_week: str      # "New step 2", "Reminder", "Heads-up", "Back on exec agenda", "Back on track", "Reset", ""
    action: str
    notes: list[str] = field(default_factory=list)


def _reset_due(h: History, today: date) -> bool:
    if h.step == 0:
        return False
    anchor = max(d for d in (h.last_off_track_date, h.last_step_date) if d)
    return (today - anchor).days >= RESET_DAYS


def decide(initiative_id: str, status: str, hist: History | None, today: date) -> tuple[Decision, History]:
    h = hist or History(initiative_id)
    before = h.step
    notes: list[str] = []

    if status == DONE:
        h.step, h.last_step_date, h.updated_on = 0, None, today
        return Decision(initiative_id, status, before, 0, "Closed" if before else "", "Close out and share the result"), h

    if _reset_due(h, today) and status != OFF_TRACK:
        notes.append(f"Ladder reset (4 weeks with no off-track week, was step {h.step})")
        h.step, h.last_step_date = 0, None

    this_week, action = "", ""
    if status == OFF_TRACK:
        h.last_off_track_date = today
        due_for_next = h.last_step_date is None or (today - h.last_step_date).days >= STEP_GAP_DAYS
        if h.step < 3 and due_for_next:
            h.step += 1
            h.last_step_date = today
            this_week, action = f"New step {h.step}", STEP_ACTION[h.step]
        elif h.step == 3 and due_for_next:
            h.last_step_date = today
            this_week, action = "Back on exec agenda", STEP_ACTION[3]
        else:
            this_week = "Reminder"
            action = f"Weekly reminder to owner (step {h.step} in place)"
    elif status == AT_RISK:
        this_week, action = "Heads-up", "Heads-up to owner, no step"
    elif notes:
        this_week = "Reset"
    elif h.step > 0:
        this_week = "Back on track"

    h.updated_on = today
    return Decision(initiative_id, status, before, h.step, this_week, action, notes), h
