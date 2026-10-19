#!/usr/bin/env python3
"""Weekly initiative review.

1. Read this week's snapshot (one row per initiative).
2. Rate every initiative: on track, at risk, off track or done.
3. Apply the escalation ladder using data/escalation-history.csv.
4. Write the week's files to out/<date>/:
     this_week.csv        every initiative with status, reasons, step and action
     owner_messages.csv   ready-to-send nudges, one per owner who needs one
     exec_update.md       the one-page update for leadership
     report.html          the same update as a page
5. Save the updated history and add a line to data/run-log.csv.
6. Push the tables to a Google Sheet (only if the sheet secrets are set).

Usage:
  python scripts/run_weekly.py --snapshot data/snapshots/2026-10-19.csv
  python scripts/run_weekly.py --snapshot file.csv --date 2026-10-19 --no-sheet
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder import AT_RISK, DONE, HISTORY_FIELDS, OFF_TRACK, ON_TRACK, History, decide, rate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "data" / "escalation-history.csv"
RUN_LOG = ROOT / "data" / "run-log.csv"
OUT_DIR = ROOT / "out"
ORDER = {OFF_TRACK: 0, AT_RISK: 1, ON_TRACK: 2, DONE: 3}


# ---------- in ----------

def read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def load_history() -> dict[str, History]:
    if not HISTORY_FILE.exists():
        return {}
    return {r["initiative_id"]: History.from_row(r) for r in read_csv(HISTORY_FILE)}


# ---------- out ----------

def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def owner_message(r: dict) -> str:
    why = "; ".join(r["reasons"]) or "it's slipping"
    if r["this_week"].startswith("New step 1"):
        ask = "Could you share a short recovery plan (what, who, new date) by Friday?"
    elif r["this_week"].startswith("New step 2"):
        ask = f"I've added it to this week's review with {r['lead']}. Please bring the recovery plan."
    elif r["step_after"] == 3:
        ask = "It's on the exec agenda this week. Please come with a recommendation: re-scope, add people, or move the date."
    elif r["status"] == AT_RISK:
        ask = "Nothing needed yet. Just flag it if you need help before it slips further."
    else:
        ask = "Still waiting on the recovery plan. Anything blocking you that I can unblock?"
    return f"Hi {r['owner'].split()[0]}, quick one on {r['name']}: it's {r['status'].lower()} ({why}). {ask}"


def exec_markdown(today: date, rows: list[dict], trend: list[dict]) -> str:
    c = Counter(r["status"] for r in rows)
    live = [r for r in rows if r["status"] != DONE]
    lines = [f"# Initiative update · week of {today:%d %b %Y}", "",
             f"**{len(live)} live initiatives:** {c[ON_TRACK]} on track, {c[AT_RISK]} at risk, "
             f"{c[OFF_TRACK]} off track. {c[DONE]} done.", ""]
    if len(trend) >= 2:
        prev = trend[-2]
        lines += [f"Off track last week: {prev['off_track']}. This week: {c[OFF_TRACK]}.", ""]
    sections = [
        ("Decisions needed (exec review)", [r for r in rows if r["step_after"] == 3 and r["status"] == OFF_TRACK]),
        ("Escalated this week", [r for r in rows if r["this_week"] in ("New step 1", "New step 2")]),
        ("Watch list (at risk)", [r for r in rows if r["status"] == AT_RISK]),
        ("Good news", [r for r in rows if (r["status"] == ON_TRACK and r["step_before"] > 0)
                       or r["this_week"] == "Closed" or (r["status"] == DONE and r["completed_this_week"])]),
    ]
    for title, items in sections:
        lines.append(f"## {title}")
        if not items:
            lines.append("- None this week.")
        for r in items:
            why = "; ".join(r["reasons"])
            extra = f" · {why}" if why else ""
            lines.append(f"- **{r['name']}** ({r['market']}, {r['owner']}){extra}")
        lines.append("")
    return "\n".join(lines)


def report_html(today: date, rows: list[dict], trend: list[dict]) -> str:
    e = html.escape
    c = Counter(r["status"] for r in rows)
    pill = {ON_TRACK: "on", AT_RISK: "risk", OFF_TRACK: "off", DONE: "done"}

    def steps(n: int) -> str:
        return "".join(f'<i class="{"lit" if i <= n else ""}"></i>' for i in (1, 2, 3))

    decisions = [r for r in rows if r["step_after"] == 3 and r["status"] == OFF_TRACK]
    tiles = "".join(f'<div class="tile {pill[s]}"><b>{c[s]}</b><span>{s}</span></div>'
                    for s in (OFF_TRACK, AT_RISK, ON_TRACK, DONE))
    bars = "".join(
        f'<div class="wk"><div class="stack" style="height:140px">'
        f'<div class="off" style="flex:{t["off_track"]}"></div><div class="risk" style="flex:{t["at_risk"]}"></div>'
        f'<div class="on" style="flex:{t["on_track"]}"></div></div><small>{date.fromisoformat(t["date"]):%d %b}</small></div>'
        for t in trend[-8:])
    dec_html = "".join(
        f'<li><b>{e(r["name"])}</b> <span class="muted">· {e(r["market"])} · {e(r["owner"])}, lead {e(r["lead"])}</span>'
        f'<br>{e("; ".join(r["reasons"]))}</li>' for r in decisions) or "<li>None this week.</li>"
    table = "".join(
        f'<tr><td><b>{e(r["name"])}</b><br><span class="muted">{e(r["workstream"])} · {e(r["market"])}</span></td>'
        f'<td>{e(r["owner"])}</td><td><span class="pill {pill[r["status"]]}">{r["status"]}</span></td>'
        f'<td class="steps">{steps(r["step_after"])}</td><td>{e(r["this_week"] or "")}</td>'
        f'<td class="muted">{e("; ".join(r["reasons"]))}</td></tr>'
        for r in rows)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Initiative Update</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#F6F7F9;--card:#fff;--text:#14161B;--muted:#6B7280;--border:#E5E7EB;
--on:#138A55;--on-bg:#E8F6EF;--risk:#B45309;--risk-bg:#FEF3C7;--off:#C2410C;--off-bg:#FFE4D6;--done:#4B5563;--done-bg:#EEF0F3}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 Inter,system-ui,sans-serif}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px 16px 48px}} h1{{font-size:22px;margin:0}} h2{{font-size:14px;margin:0 0 10px}}
.muted{{color:var(--muted)}} .badge{{font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px;background:#FEF3C7;color:#92400E;margin-left:8px;vertical-align:middle}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:12px}}
.top{{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:12px;margin:18px 0 12px}}
.tiles{{display:grid;grid-template-columns:1fr 1fr;gap:8px}} .tile{{border-radius:10px;padding:10px 12px}}
.tile b{{display:block;font-size:26px;line-height:1.1}} .tile span{{font-size:12px;font-weight:600}}
.tile.on{{background:var(--on-bg);color:var(--on)}} .tile.risk{{background:var(--risk-bg);color:var(--risk)}}
.tile.off{{background:var(--off-bg);color:var(--off)}} .tile.done{{background:var(--done-bg);color:var(--done)}}
.trend{{display:flex;align-items:flex-end;gap:14px;height:170px;padding-top:6px}} .wk{{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1}}
.stack{{width:100%;max-width:38px;display:flex;flex-direction:column;border-radius:6px;overflow:hidden}}
.stack .off{{background:var(--off)}} .stack .risk{{background:#F59E0B}} .stack .on{{background:#34B37A}}
.legend{{font-size:12px;color:var(--muted);margin-top:6px}} .legend i{{display:inline-block;width:8px;height:8px;border-radius:2px;margin:0 4px 0 10px}}
.decisions ul{{margin:0;padding-left:18px}} .decisions li{{margin-bottom:8px}}
.ladder{{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;font-size:12px}} .ladder div{{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:6px 8px;flex:1;min-width:120px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{text-align:left;padding:9px 8px;border-bottom:1px solid var(--border);vertical-align:top}}
th{{color:var(--muted);font-weight:500;font-size:12px}} .tw{{overflow-x:auto}}
.pill{{font-size:12px;font-weight:600;padding:2px 8px;border-radius:99px;white-space:nowrap}}
.pill.on{{background:var(--on-bg);color:var(--on)}} .pill.risk{{background:var(--risk-bg);color:var(--risk)}}
.pill.off{{background:var(--off-bg);color:var(--off)}} .pill.done{{background:var(--done-bg);color:var(--done)}}
.steps{{white-space:nowrap}} td:nth-child(5),td:nth-child(3){{white-space:nowrap}} .wk small{{white-space:nowrap}} .steps i{{display:inline-block;width:14px;height:6px;border-radius:3px;background:var(--border);margin-right:3px}} .steps i.lit{{background:var(--off)}}
@media (max-width:860px){{.top{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Initiative update · week of {today:%d %b %Y} <span class="badge">Demo data</span></h1>
<div class="muted">Generated automatically every Monday from the project tracker</div>
<div class="top">
  <div class="card"><h2>This week</h2><div class="tiles">{tiles}</div></div>
  <div class="card"><h2>Status trend</h2><div class="trend">{bars}</div>
    <div class="legend"><i style="background:var(--off)"></i>Off track<i style="background:#F59E0B"></i>At risk<i style="background:#34B37A"></i>On track</div></div>
  <div class="card decisions"><h2>Decisions needed at exec review</h2><ul>{dec_html}</ul></div>
</div>
<div class="card"><h2>Escalation ladder</h2><div class="muted">Only off-track projects climb. Next step only if still off track 14+ days later. Resets after 4 clean weeks.</div>
<div class="ladder"><div><b>Step 1</b><br>Nudge owner, recovery plan by Friday</div><div><b>Step 2</b><br>Flag to lead, joint review</div><div><b>Step 3</b><br>Exec review: re-scope, re-resource or re-date</div></div></div>
<div class="card"><h2>All initiatives</h2><div class="tw"><table>
<tr><th>Initiative</th><th>Owner</th><th>Status</th><th>Step</th><th>This week</th><th>Why</th></tr>{table}</table></div></div>
</div></body></html>"""


def push_to_sheet(tabs: dict[str, list[list]]) -> None:
    """Write each tab to the Google Sheet. Skipped if the secrets aren't set."""
    sa, sheet_id = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"), os.environ.get("GOOGLE_SHEET_ID")
    if not (sa and sheet_id):
        print("Google Sheet secrets not set, skipping the sheet.")
        return
    import gspread  # only needed when the sheet is used
    sh = gspread.service_account_from_dict(json.loads(sa)).open_by_key(sheet_id)
    for name, values in tabs.items():
        try:
            ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(name, rows=200, cols=12)
        ws.clear()
        ws.update(values, "A1")
    print(f"Google Sheet updated ({', '.join(tabs)}).")


# ---------- main ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True, type=Path)
    ap.add_argument("--date", help="run date YYYY-MM-DD (default: today)")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--force", action="store_true", help="run even if this date already ran")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    log = read_csv(RUN_LOG) if RUN_LOG.exists() else []
    log = [{k: (v if k == "date" else int(v)) for k, v in r.items()} for r in log]
    if any(r["date"] == today.isoformat() for r in log) and not args.force:
        sys.exit(f"Already ran for {today}. Use --force to run again (steps would be applied twice).")

    history = load_history()
    rows = []
    for p in read_csv(args.snapshot):
        status, reasons = rate(p, today)
        d, h = decide(p["initiative_id"], status, history.get(p["initiative_id"]), today)
        history[p["initiative_id"]] = h
        rows.append({**p, "status": status, "reasons": reasons + d.notes,
                     "step_before": d.step_before, "step_after": d.step_after,
                     "this_week": d.this_week, "action": d.action,
                     "completed_this_week": status == DONE and
                                            (today - date.fromisoformat(p["last_update"])).days <= 7})
    rows.sort(key=lambda r: (ORDER[r["status"]], -r["step_after"], r["name"]))

    out = OUT_DIR / today.isoformat()
    week_fields = ["initiative_id", "name", "workstream", "market", "owner", "lead", "due_date",
                   "progress_pct", "status", "why", "step", "this_week", "action"]
    week_rows = [{**{k: r[k] for k in week_fields if k in r}, "why": "; ".join(r["reasons"]),
                  "step": r["step_after"]} for r in rows]
    write_csv(out / "this_week.csv", week_rows, week_fields)

    msgs = [{"owner": r["owner"], "initiative": r["name"], "message": owner_message(r)}
            for r in rows if r["status"] in (OFF_TRACK, AT_RISK)]
    write_csv(out / "owner_messages.csv", msgs, ["owner", "initiative", "message"])

    c = Counter(r["status"] for r in rows)
    log.append({"date": today.isoformat(), "total": len(rows), "on_track": c[ON_TRACK],
                "at_risk": c[AT_RISK], "off_track": c[OFF_TRACK], "done": c[DONE],
                "new_steps": sum(r["this_week"].startswith("New step") for r in rows)})
    (out / "exec_update.md").write_text(exec_markdown(today, rows, log))
    (out / "report.html").write_text(report_html(today, rows, log))


    write_csv(HISTORY_FILE, [h.to_row() for h in sorted(history.values(), key=lambda h: h.initiative_id)], HISTORY_FIELDS)
    write_csv(RUN_LOG, log, ["date", "total", "on_track", "at_risk", "off_track", "done", "new_steps"])

    if not args.no_sheet:
        table = lambda rs, fs: [fs] + [[r.get(f, "") for f in fs] for r in rs]  # noqa: E731
        push_to_sheet({
            "This week": table(week_rows, week_fields),
            "Owner messages": table(msgs, ["owner", "initiative", "message"]),
            "History": table([h.to_row() for h in history.values()], HISTORY_FIELDS),
            "Run log": table(log, list(log[0].keys())),
        })

    import build_site  # refresh the interactive page's data
    build_site.main()
    print(f"{today}: {c[OFF_TRACK]} off track, {c[AT_RISK]} at risk, {c[ON_TRACK]} on track, {c[DONE]} done. "
          f"Files in {out.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
