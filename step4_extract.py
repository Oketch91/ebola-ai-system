"""Step 4: AI extraction of cases from one report, with analyst review.

Works on a SEPARATE replay line list (data/replay_linelist.csv), so the
verified Kenyan line list used in the paper is never changed.

1. Set REPORT below to a file in the reports folder.
2. Press F5. Claude proposes new cases with the sentence each came from.
3. In the console, approve (a), reject (r) or correct (field=value) each one.
4. Approved cases are added to the replay line list; every decision is
   logged in data/audit_log.csv.
Run the reports in date order. To start the replay again, set RESET = True.
"""
import os
import shutil

import pandas as pd

from ebola.extraction import apply_approved, extract, review_in_console

REPORT = "reports/2026-10-06_MoH.txt"     # change for each report
ANALYST = "F. Ochieng"
RESET = False                              # True: start the replay from an empty line list

LINELIST = "data/replay_linelist.csv"
AUDIT = "data/audit_log.csv"
if RESET or not os.path.exists(LINELIST):
    shutil.copy("data/replay_linelist_start.csv", LINELIST)
    if os.path.exists(AUDIT):
        os.remove(AUDIT)
    print("Replay line list reset to empty.")

name = os.path.basename(REPORT)
report_date, source = name[:10], name[11:].replace(".txt", "")
text = open(REPORT, encoding="utf-8").read()
linelist = pd.read_csv(LINELIST, parse_dates=["confirm_date", "onset_date"])

proposal = extract(text, report_date, source, linelist)
reviewed = review_in_console(proposal)
if not reviewed.empty:
    ll = apply_approved(reviewed, proposal, LINELIST, AUDIT, ANALYST)
    print(ll.to_string(index=False))
