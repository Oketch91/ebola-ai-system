"""Day-by-day replay for the colloquium: re-estimate the model as it would
have been on each day of the outbreak, using only the cases known that day.

First rebuilds data/replay_linelist.csv from the reports folder (runs replay.py),
then re-estimates day by day. Press F5 in Spyder; takes about 5 minutes.
Results: results/replay_history.csv and a figure of how the estimates evolved.
"""
import json
import os
import runpy

import matplotlib.pyplot as plt
import pandas as pd

from ebola.analysis import save_estimates, update_estimates

START, END = "2026-10-06", "2026-10-30"
LINELIST = "data/replay_linelist.csv"

runpy.run_path("replay.py")              # rebuild the replay line list from the reports
ll = pd.read_csv(LINELIST)
hist_path = "results/replay_history.csv"
if os.path.exists(hist_path):
    os.remove(hist_path)
curves = {}
for day in pd.date_range(START, END):
    res = update_estimates(ll, day)
    save_estimates(res, "results", history_name="replay_history.csv", latest=False)
    if "curve_p" in res:
        curves[res["cutoff"]] = (res["curve_days"], res["curve_p"])
    print(f"{res['cutoff']}: {res['cases']} cases, Rc {res['Rc'][0]:.2f}, "
          f"incubation {res['incubation_days'][0]:.1f} d, P(over) {res.get('P_over_today', '-')}")
json.dump(curves, open("results/replay_curves.json", "w"))

h = pd.read_csv(hist_path, parse_dates=["cutoff"])
fig, ax = plt.subplots(2, 2, figsize=(12, 7), sharex=True)
ax[0, 0].bar(h["cutoff"], h["cases"], color="grey")
ax[0, 0].set_ylabel("Confirmed cases (cumulative)")
for a, k, lab in [(ax[0, 1], "Rc", "Control reproduction number $R_c$"),
                  (ax[1, 0], "incubation_days", "Mean incubation period (days)")]:
    a.plot(h["cutoff"], h[f"{k}_median"], lw=1.5)
    a.fill_between(h["cutoff"], h[f"{k}_lo"], h[f"{k}_hi"], alpha=0.25)
    a.set_ylabel(lab)
ax[0, 1].axhline(1, color="r", ls="--", lw=1)
ax[1, 1].plot(h["cutoff"], h["P_over_today"], lw=1.5)
ax[1, 1].axhline(0.95, color="r", ls="--", lw=1)
ax[1, 1].set_ylim(0, 1); ax[1, 1].set_ylabel("P(transmission has ended)")
for a in ax.flat:
    a.grid(alpha=0.3); a.tick_params(axis="x", rotation=30)
fig.suptitle("How the estimates evolved as the data arrived (Kenya, October 2026)")
fig.tight_layout()
fig.savefig("results/replay_history.png", dpi=150)
plt.show()
