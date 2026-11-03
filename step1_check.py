"""Step 1 check: the Python model must reproduce the MATLAB results.

Run this file in Spyder (F5). Expected MATLAB values are printed beside
the Python values.
"""
import matplotlib.pyplot as plt
import numpy as np

from ebola.data import build_data, load_line_list
from ebola.model import analytics, early_growth, run_deterministic, seihdr_rhs
from ebola.parameters import Params, with_incubation

P = Params()

# Data
ll = load_line_list("data/kenya_linelist.csv")
D = build_data(ll, "2026-10-30")
print(f"Data: {int(D.y_hh.sum() + D.y_hcw.sum())} secondary cases "
      f"({int(D.y_hh.sum())} household, {int(D.y_hcw.sum())} health care), "
      f"last confirmed on day {D.last_case_day}   [MATLAB: 8 (4, 4), day 16]")
print(f"Onset days: {D.onset_sec.tolist()}   [MATLAB: 10 10 13 13 13 13 14 15]")
print(f"Last day of data: {D.t_obs}   [MATLAB: 27]")

# Analytics
A = analytics(P, P.epsH_default)
print(f"\nR0 = {A.R0:.2f} (community {A.RI:.2f}, hospital {A.RH:.2f}, funeral {A.RD:.2f}); "
      f"NGM check {A.R0_ngm:.2f}   [MATLAB: 1.98 (0.47, 0.67, 0.84); 1.98]")
print(f"CFR_I = {A.CFR_I:.3f}, CFR_H = {A.CFR_H:.3f}, CFR = {A.CFR:.3f}, IFR = {A.IFR:.3f}"
      f"   [MATLAB: 0.386, 0.383, 0.383, 0.383]")
resid = np.max(np.abs(seihdr_rhs(0, A.EE, P)))
print(f"EE: S*/N* = {A.EE[0] / A.EE[[0, 1, 2, 3, 5]].sum():.4f} = 1/R0 = {1 / A.R0:.4f}; "
      f"max residual {resid:.1e}   [MATLAB: 0.5038; 1e-13]")

# Early growth and deterministic run with the Kenyan incubation estimate
Pmed = with_incubation(P, 13.61)
print(f"\nDoubling time: {np.log(2) / early_growth(P):.1f} days (incubation 8.5), "
      f"{np.log(2) / early_growth(Pmed):.1f} days (incubation 13.6)   [MATLAB: 17.4, 21.7]")
t, Y = run_deterministic(Pmed, 150)
cum = P.N0 - Y[0]
print(f"Deterministic, no response: {cum[-1]:.0f} infections after 150 days   [MATLAB: 290]")

fig, ax = plt.subplots(figsize=(9, 4))
ax.semilogy(t, np.maximum(Y[2] + Y[3], 1e-3), lw=1.5, label="Prevalent cases (I + H)")
ax.semilogy(t, np.maximum(cum, 1e-3), "--", lw=1.5, label="Cumulative infections")
ax.set_xlabel("Days since arrival of index case"); ax.set_ylabel("Number of people")
ax.set_title("SEIHDR model without a response (Python)"); ax.grid(True, which="both", alpha=0.3)
ax.legend(loc="lower right"); fig.tight_layout(); plt.show()
