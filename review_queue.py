"""Review cases the watcher held back (auto mode). Press F5 in Spyder.

For each held report, approve (a), reject (r) or correct (field=value)
each case. Approved cases are added to the live line list.
"""
import json
import os

import pandas as pd

from ebola.extraction import Proposal, apply_approved, apply_updates, review_in_console

ANALYST = "F. Ochieng"
QUEUE, LIVE, AUDIT = "data/review_queue.json", "data/live_linelist.csv", "data/audit_log_live.csv"

queue = json.load(open(QUEUE, encoding="utf-8")) if os.path.exists(QUEUE) else []
if not queue:
    print("Nothing awaiting review.")
remaining = []
for entry in queue:
    print(f"\nSource: {entry['url']}")
    p = Proposal(entry["report_date"], entry["source"], entry["totals"],
                 pd.DataFrame(entry["cases"]), entry.get("notes", ""))
    if entry["cases"]:
        apply_approved(review_in_console(p), p, LIVE, AUDIT, ANALYST)
    if entry.get("death_gap"):
        live = pd.read_csv(LIVE)
        print(f"\nThe report states {entry['totals'].get('deaths')} deaths; "
              f"{entry['death_gap']} cannot be matched to a case.")
        if entry.get("notes"):
            print(f"Model notes: {entry['notes']}")
        print(live[["case_id", "confirm_date", "setting", "outcome"] +
                   [c for c in ["description"] if c in live.columns]].to_string(index=False))
        for _ in range(entry["death_gap"]):
            cid = input("  case_id of the person who died (Enter to skip): ").strip()
            if cid:
                d = input("  date of death YYYY-MM-DD (Enter if unknown): ").strip()
                apply_updates(pd.DataFrame([{"case_id": cid, "outcome": "died", "outcome_date": d,
                                             "evidence": "assigned by analyst", "issues": "",
                                             "decision": "approve"}]), p, LIVE, AUDIT, ANALYST)
    ups = pd.DataFrame(entry.get("updates", []))
    if not ups.empty:
        dec = []
        for _, u in ups.iterrows():
            print(f"\nOutcome update: {u['case_id']} -> {u['outcome']} on {u['outcome_date'] or '(date not stated)'}")
            print(f"  evidence \"{u['evidence']}\"\n  ISSUES   {u['issues']}")
            dec.append("approve" if input("  [a]pprove or [r]eject: ").strip().lower() == "a" else "reject")
        apply_updates(ups.assign(decision=dec), p, LIVE, AUDIT, ANALYST)
json.dump(remaining, open(QUEUE, "w", encoding="utf-8"))
