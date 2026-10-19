#!/usr/bin/env python3
"""Build site-data.json, the single data file behind the interactive page (index.html).

Packs every weekly run in out/<date>/ (plus the snapshots it was built from)
into one JSON file. Runs at the end of each weekly run, or on its own:
  python scripts/build_site.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open() as f:
        return list(csv.DictReader(f))


def main() -> None:
    weeks = sorted(p.name for p in (ROOT / "out").iterdir() if (p / "this_week.csv").exists())
    projects, rows, messages, updates = {}, {}, {}, {}
    for w in weeks:
        snap = {r["initiative_id"]: r for r in read(ROOT / "data" / "snapshots" / f"{w}.csv")}
        rows[w] = []
        for r in read(ROOT / "out" / w / "this_week.csv"):
            pid, s = r["initiative_id"], snap.get(r["initiative_id"], {})
            projects[pid] = {k: r[k] for k in ("name", "workstream", "market", "owner", "lead")}
            projects[pid]["start"] = s.get("start_date", "")
            rows[w].append({"id": pid, "status": r["status"], "why": r["why"], "step": int(r["step"] or 0),
                            "week": r["this_week"], "action": r["action"], "due": r["due_date"],
                            "progress": int(float(r["progress_pct"])), "last_update": s.get("last_update", ""),
                            "blockers": int(s.get("open_blockers") or 0), "blocker_note": s.get("blocker_note", "")})
        messages[w] = {m["initiative"]: m["message"] for m in read(ROOT / "out" / w / "owner_messages.csv")}
        md = ROOT / "out" / w / "exec_update.md"
        updates[w] = md.read_text() if md.exists() else ""
    out = {"weeks": weeks, "projects": projects, "rows": rows, "messages": messages, "exec_update": updates}
    (ROOT / "site-data.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"site-data.json: {len(weeks)} weeks, {len(projects)} projects")


if __name__ == "__main__":
    main()
