#!/usr/bin/env python3
"""Make four weeks of invented project snapshots in data/snapshots/.

A snapshot is what a team's project tool or tracking sheet would export
each Monday: one row per initiative with owner, dates, % done, last update
and open blockers. Every name and project here is invented.

Each project follows a story (steady, slipping, stalled, recovering...) so
the ladder has something real to do across the four weeks.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "snapshots"
WEEKS = [date(2026, 9, 14) + timedelta(weeks=i) for i in range(6)]
FIELDS = ["initiative_id", "name", "workstream", "market", "owner", "lead",
          "start_date", "due_date", "progress_pct", "last_update", "open_blockers", "blocker_note"]

# id, name, workstream, market, owner, lead, start, due, story
# story = weekly tuples for the last 4 weeks; EARLY adds the 2 weeks before
# (default: the first week, at half the slippage)
# story = 4 weekly tuples: (points behind plan, days since update, open blockers, blocker note)
P = [
    ("IN-01", "Local payment methods", "Payments", "India", "Arjun K.", "Priya R.", "2026-07-01", "2026-12-15",
     [(4, 3, 0, ""), (12, 5, 1, "Bank API access pending"), (27, 4, 2, "Bank API access pending; legal review"), (33, 6, 2, "Bank API access pending; legal review")]),
    ("IN-02", "Referral program v2", "Growth marketing", "India", "Neha S.", "Priya R.", "2026-08-15", "2026-11-30",
     [(2, 2, 0, ""), (3, 4, 0, ""), (1, 2, 0, ""), (0, 3, 0, "")]),
    ("JP-01", "Loyalty tier relaunch", "Product", "Japan", "Hana S.", "Kenji M.", "2026-06-01", "2026-11-10",
     [(8, 6, 0, ""), (14, 9, 1, "Design sign-off"), (11, 4, 0, ""), (6, 2, 0, "")]),
    ("JP-02", "Enterprise partner pilot", "Partnerships", "Japan", "Daniel O.", "Kenji M.", "2026-07-15", "2026-10-31",
     [(5, 4, 0, ""), (9, 11, 0, ""), (18, 18, 0, ""), (26, 25, 0, "")]),
    ("JP-03", "Help centre translation", "Brand", "Japan", "Yui T.", "Kenji M.", "2026-08-01", "2026-10-15",
     [(3, 2, 0, ""), (0, 3, 0, ""), (0, 1, 0, ""), (0, 0, 0, "")]),
    ("KR-01", "Local pricing rollout", "Product", "Korea", "Minjun P.", "Sofia L.", "2026-08-01", "2026-10-20",
     [(6, 3, 0, ""), (8, 2, 1, "App store approval"), (4, 2, 0, ""), (2, 1, 0, "")]),
    ("KR-02", "Data residency compliance", "Policy", "Korea", "Jiwoo L.", "Sofia L.", "2026-05-01", "2026-10-10",
     [(22, 8, 1, "Regulator feedback"), (30, 6, 2, "Regulator feedback; vendor contract"), (100, 5, 2, "Regulator feedback; vendor contract"), (100, 9, 2, "Regulator feedback; vendor contract")]),
    ("KR-03", "Creator onboarding flow", "Supply", "Korea", "Seo-yeon H.", "Sofia L.", "2026-09-01", "2027-01-31",
     [(0, 2, 0, ""), (2, 3, 0, ""), (1, 5, 0, ""), (3, 4, 0, "")]),
    ("SEA-01", "Market entry: Vietnam", "Market launch", "Southeast Asia", "Linh N.", "Marco D.", "2026-06-15", "2027-02-28",
     [(10, 5, 1, "Entity setup"), (16, 7, 1, "Entity setup"), (27, 8, 2, "Entity setup; tax registration"), (31, 10, 2, "Entity setup; tax registration")]),
    ("SEA-02", "Wallet partnership", "Partnerships", "Southeast Asia", "Rizal A.", "Marco D.", "2026-08-01", "2026-12-20",
     [(27, 23, 0, ""), (29, 30, 0, ""), (15, 3, 1, "Contract redlines"), (8, 2, 0, "")]),
    ("SEA-03", "Promo engine for campaigns", "Growth marketing", "Southeast Asia", "Thida W.", "Marco D.", "2026-07-01", "2026-11-15",
     [(5, 4, 0, ""), (7, 4, 0, ""), (12, 5, 0, ""), (13, 12, 0, "")]),
    ("RG-01", "Regional reporting cadence", "Operations", "Regional", "Aisha B.", "Marco D.", "2026-08-15", "2026-11-01",
     [(0, 1, 0, ""), (2, 2, 0, ""), (0, 1, 0, ""), (0, 1, 0, "")]),
    ("RG-02", "Competitor price tracker", "Operations", "Regional", "Tom W.", "Priya R.", "2026-09-01", "2026-12-01",
     [(3, 3, 0, ""), (2, 2, 0, ""), (4, 6, 0, ""), (2, 3, 0, "")]),
    ("RG-03", "Brand refresh assets", "Brand", "Regional", "Lea M.", "Sofia L.", "2026-07-01", "2026-10-30",
     [(9, 6, 0, ""), (12, 8, 0, ""), (14, 12, 1, "Agency capacity"), (24, 15, 1, "Agency capacity")]),
]


EARLY = {
    "KR-02": [(26, 7, 2, "Regulator feedback; vendor contract"), (24, 9, 2, "Regulator feedback; vendor contract")],
    "SEA-02": [(12, 9, 0, ""), (20, 16, 0, "")],
}


def full_story(pid: str, story: list) -> list:
    if pid in EARLY:
        return EARLY[pid] + story
    b, st, bl, note = story[0]
    return [(b // 2, min(st, 4), 0, ""), (b // 2, min(st, 5), 0, "")] + story


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    from ladder import planned_pct  # same maths as the tracker
    for wk, monday in enumerate(WEEKS):
        rows = []
        for pid, name, ws, mkt, owner, lead, start, due, story in P:
            behind, stale, blockers, note = full_story(pid, story)[wk]
            plan = planned_pct(date.fromisoformat(start), date.fromisoformat(due), monday)
            progress = 100 if (plan >= 100 and behind == 0) else max(0, min(99, round(plan - behind)))
            if behind >= 100:  # past due, stuck
                progress = 72
            rows.append({"initiative_id": pid, "name": name, "workstream": ws, "market": mkt,
                         "owner": owner, "lead": lead, "start_date": start, "due_date": due,
                         "progress_pct": progress, "last_update": (monday - timedelta(days=stale)).isoformat(),
                         "open_blockers": blockers, "blocker_note": note})
        path = OUT / f"{monday.isoformat()}.csv"
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
