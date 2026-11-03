"""Step 3 check: scenario analyses and the probability that the outbreak has
ended, compared with the MATLAB results.

Uses the posterior saved by step2_check.py (posterior_step2.npz); if that file
is missing, the MCMC is run first. Takes under a minute.
The end-of-outbreak curve uses 100 000 simulations and runs to 90 days, so
the 0.95 and 0.99 thresholds are estimated precisely.
"""
import os
import time

import matplotlib.pyplot as plt
import numpy as np

from ebola.data import build_data, load_line_list
from ebola.inference import fit
from ebola.parameters import Params
from ebola.simulation import define_scenarios, end_of_outbreak, run_scenarios

P = Params()
D = build_data(load_line_list("data/kenya_linelist.csv"), "2026-10-30")
if os.path.exists("posterior_step2.npz"):
    post = np.load("posterior_step2.npz")["post"]
else:
    post, _, _ = fit(D, P)
rng = np.random.default_rng(2026)

# Scenario analyses
matlab_p20 = [0.242, 0.249, 0.327, 0.541, 0.312, 0.395, 0.475, 0.352]
matlab_p100 = [0.005, 0.004, 0.008, 0.013, 0.010, 0.021, 0.040, 0.008]
t0 = time.time()
res = run_scenarios(post, P, D, rng)
print(f"Scenarios finished in {time.time() - t0:.0f} s\n")
scs = define_scenarios(P)
for k, sc in enumerate(scs):
    r = res[sc.name]
    qc = np.quantile(r.cum_cases, [0.5, 0.025, 0.975])
    qd = np.quantile(r.cum_deaths, [0.5, 0.025, 0.975])
    print(f"{sc.name:<30} cases {qc[0]:4.0f} ({qc[1]:3.0f}-{qc[2]:4.0f})  deaths {qd[0]:3.0f} ({qd[1]:2.0f}-{qd[2]:3.0f})"
          f"  P(>20) {np.mean(r.cum_cases > 20):.3f} [{matlab_p20[k]:.3f}]"
          f"  P(>100) {np.mean(r.cum_cases > 100):.3f} [{matlab_p100[k]:.3f}]")

# Probability that the outbreak has ended
t0 = time.time()
days_since, p_ended, n_keep = end_of_outbreak(post, P, D, rng, n_sim=100_000, max_days=90)
print(f"\nEnd of outbreak ({time.time() - t0:.0f} s): {n_keep} of 100000 simulations consistent with the data   [MATLAB: 5570 of 10000]")
get = lambda d: p_ended[days_since == d][0]
d_today = D.t_obs - D.last_onset_day
first = lambda thr: (f"{days_since[np.argmax(p_ended >= thr)]} days"
                     if np.any(p_ended >= thr) else f"not reached by {days_since[-1]} days")
print(f"P(over) on 30 Oct ({d_today} days after last onset): {get(d_today):.3f}   [MATLAB: 0.629]")
print(f"P(over) at 42 days: {get(42):.4f}   [MATLAB: 0.9589]")
print(f"P(over) at 60 days: {get(60):.4f}")
print(f"First >= 0.95: {first(0.95)}; first >= 0.99: {first(0.99)}   [MATLAB: 40, 60]")

np.savez("simulation_step3.npz", days_since=days_since, p_ended=p_ended,
         **{f"cases_{k}": res[sc.name].cum_cases for k, sc in enumerate(scs)})

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
p20 = [np.mean(res[sc.name].cum_cases > 20) for sc in scs]
p100 = [np.mean(res[sc.name].cum_cases > 100) for sc in scs]
x = np.arange(len(scs))
axes[0].bar(x - 0.2, p20, 0.4, label="More than 20 cases")
axes[0].bar(x + 0.2, p100, 0.4, label="More than 100 cases")
axes[0].set_xticks(x, [sc.short for sc in scs], rotation=30)
axes[0].set_ylabel("Probability"); axes[0].legend(); axes[0].grid(alpha=0.3)
axes[0].set_title("Outbreak size by scenario")
axes[1].plot(days_since, p_ended, lw=1.5, label="Model")
axes[1].axvline(42, color="r", ls="--", label="WHO 42-day rule")
axes[1].set_ylim(0, 1); axes[1].set_xlabel("Days since onset of the last case")
axes[1].set_ylabel("Probability transmission has ended"); axes[1].legend(loc="lower right")
axes[1].grid(alpha=0.3); axes[1].set_title("Probability the outbreak has ended")
fig.tight_layout(); plt.show()
