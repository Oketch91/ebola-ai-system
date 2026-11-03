"""Step 2 check: the Python MCMC must reproduce the MATLAB posterior.

Takes about 1-3 minutes. Results agree with MATLAB within Monte Carlo error
(the random numbers differ), so expect the second decimal to vary slightly.
"""
import time

import matplotlib.pyplot as plt
import numpy as np

from ebola.data import build_data, load_line_list
from ebola.inference import NAMES, expected_confirmations, fit, rc_posterior
from ebola.parameters import Params

P = Params()
D = build_data(load_line_list("data/kenya_linelist.csv"), "2026-10-30")

t0 = time.time()
post, chains, rhat = fit(D, P)
print(f"MCMC finished in {time.time() - t0:.0f} s")

matlab = ["4.73 (1.62-10.32)", "4.69 (1.64-10.30)", "0.81 (0.15-0.99)", "13.61 (10.77-16.24)"]
print("\nPosterior medians (95% CrI) and R-hat")
for k in range(4):
    q = np.quantile(post[:, k], [0.5, 0.025, 0.975])
    print(f"{NAMES[k]:<45} {q[0]:6.2f} ({q[1]:5.2f}-{q[2]:5.2f})  R-hat {rhat[k]:.3f}   [MATLAB: {matlab[k]}]")
q = np.quantile(post[:, 0] + post[:, 1], [0.5, 0.025, 0.975])
print(f"{'Total offspring of index case':<45} {q[0]:6.2f} ({q[1]:5.2f}-{q[2]:5.2f})   [MATLAB: 9.73 (4.83-17.09)]")
rc = rc_posterior(post, P)
q = np.quantile(rc, [0.5, 0.025, 0.975])
print(f"{'Control reproduction number Rc':<45} {q[0]:6.2f} ({q[1]:5.2f}-{q[2]:5.2f})   [MATLAB: 0.18 (0.05-0.67)]")
print(f"P(Rc < 1) = {np.mean(rc < 1):.4f}, P(Rc < 0.5) = {np.mean(rc < 0.5):.3f}   [MATLAB: 1.0000, 0.908]")
mu_hh, mu_hcw = expected_confirmations(np.median(post, axis=0), D, P)
e10 = mu_hh[:11].sum() + mu_hcw[:11].sum()
print(f"Expected confirmations by 13 Oct: {e10:.2f}; P(none) = {np.exp(-e10):.2f}   [MATLAB: 1.23; 0.29]")

np.savez("posterior_step2.npz", post=post, rc=rc, rhat=rhat)
print("Posterior saved to posterior_step2.npz")

# Trace plots (convergence check)
fig, axes = plt.subplots(4, 1, figsize=(9, 8), sharex=True)
for k, ax in enumerate(axes):
    for c in chains:
        ax.plot(c.samples[::50, k], lw=0.5)
    ax.set_ylabel(["mI", "mH", "epsH", "Incubation"][k])
axes[-1].set_xlabel("Iteration (every 50th)")
fig.suptitle("MCMC trace plots, 4 chains"); fig.tight_layout(); plt.show()
