"""Replay the outbreak automatically: every report in the reports folder is
processed in date order, with no manual steps. Press F5 in Spyder.

Cases that pass every check are added automatically (MODE = "auto").
Any case that fails a check is shown for review at the end, so you only
see the problem cases. Set ASK_ABOUT_HELD = False to skip even that.
At the end, the replay line list is compared with the verified one.
"""
import glob
import os
import shutil

import pandas as pd

from ebola.extraction import (apply_approved, apply_updates, auto_decide,
                               auto_decide_updates, extract, review_in_console)

MODE = "auto"              # "auto" or "full" (approve everything)
ASK_ABOUT_HELD = False     # True: review held cases at the end
ANALYST = "F. Ochieng"

LINELIST, AUDIT = "data/replay_linelist.csv", "data/audit_log.csv"
shutil.copy("data/replay_linelist_start.csv", LINELIST)
if os.path.exists(AUDIT):
    os.remove(AUDIT)

held = []
for path in sorted(glob.glob("reports/????-??-??_*.txt")):
    name = os.path.basename(path)
    report_date, source = name[:10], name[11:].replace(".txt", "")
    ll = pd.read_csv(LINELIST, parse_dates=["confirm_date", "onset_date"])
    p = extract(open(path, encoding="utf-8").read(), report_date, source, ll)
    decided = auto_decide(p, ll, MODE)
    if not decided.empty:
        apply_approved(decided, p, LINELIST, AUDIT, "auto", verbose=False)
    upd = auto_decide_updates(p, MODE)
    n_upd = apply_updates(upd, p, LINELIST, AUDIT, "auto")
    for _, u in upd[upd.get("decision", pd.Series(dtype=str)) == "hold"].iterrows():
        print(f"    outcome update held: {u['case_id']} {u['outcome']} ({u['issues']})")
    n_ok = int((decided["decision"] == "approve").sum()) if not decided.empty else 0
    n_hold = len(decided) - n_ok
    print(f"{report_date} {source}: {len(decided)} new, {n_ok} added, {n_hold} held, "
          f"{n_upd} outcome update(s) "
          f"(report total {p.totals.get('confirmed_cases')}, line list "
          f"{len(pd.read_csv(LINELIST))})")
    if n_hold:
        p.cases = decided[decided["decision"] == "hold"].drop(columns="decision").reset_index(drop=True)
        held.append(p)

if held and ASK_ABOUT_HELD:
    print(f"\n{len(held)} report(s) had cases that failed a check:")
    for p in held:
        apply_approved(review_in_console(p), p, LINELIST, AUDIT, ANALYST)

# Compare with the verified line list
rep = pd.read_csv(LINELIST)
ver = pd.read_csv("data/kenya_linelist.csv")
cols = ["role", "setting", "confirm_date", "outcome"]
key = lambda d: sorted(map(tuple, d[cols].astype(str).values))
print(f"\nReplay line list: {len(rep)} cases; verified line list: {len(ver)} cases")
print("Roles, settings, confirmation dates and outcomes match the verified line list."
      if key(rep) == key(ver) else "DIFFERENCES from the verified line list:")
if key(rep) != key(ver):
    print(pd.concat([rep[cols].assign(list="replay"), ver[cols].assign(list="verified")])
          .drop_duplicates(subset=cols, keep=False).to_string(index=False))
print(rep.to_string(index=False))
