"""Discrete-time stochastic SEIHDR model (daily chain-binomial) with traced (t)
and untraced (u) classes, the scenario analyses and the probability that the
outbreak has ended.

All simulations of a scenario run together as arrays (one element per
simulation), which is much faster in Python than a loop over simulations.
"""
from dataclasses import dataclass, replace

import numpy as np

from .data import ObsData
from .model import exit_rates
from .parameters import Params


@dataclass(frozen=True)
class Scenario:
    name: str
    short: str
    tStar: int
    fTrace: float = 1.0
    unsafe_funeral: bool = False
    from_data: bool = False


def define_scenarios(P: Params):
    """Observed response and counterfactual scenarios."""
    base = Scenario("Observed response", "Observed", P.tStar)
    sc = [base]
    for d in (3, 7, 14):
        sc.append(replace(base, name=f"Detection delayed {d} days", short=f"Delay {d}d", tStar=P.tStar + d))
    for f in (0.8, 0.6, 0.4):
        sc.append(replace(base, name=f"Tracing {round(100 * f)}%", short=f"Trace {round(100 * f)}%", fTrace=f))
    sc.append(replace(base, name="Unsafe funeral of index case", short="Funeral", unsafe_funeral=True))
    return sc


def _split(rng, n, total_rate, rates):
    """Numbers leaving a compartment in one day, split among competing exits.
    n: array (nSim); total_rate: array or scalar; rates: list of arrays/scalars."""
    n_out = rng.binomial(n, 1 - np.exp(-total_rate))
    out, remaining = [], n_out
    rsum = sum(rates)
    for r in rates[:-1]:
        pk = np.clip(np.divide(r, rsum, out=np.zeros_like(rsum * 1.0), where=rsum > 0), 0, 1)
        x = rng.binomial(remaining, pk)
        out.append(x)
        remaining = remaining - x
        rsum = rsum - r
    out.append(remaining)
    return out


@dataclass
class SimResult:
    cum_cases: np.ndarray       # final cases per simulation (index case included)
    cum_deaths: np.ndarray      # final deaths per simulation (index case included)
    onsets: np.ndarray          # new (unobserved) onsets per day, nSim x (Tmax+1)


def simulate(theta, P: Params, sc: Scenario, D: ObsData, rng,
             Tmax: int = 365, cap: int = 5000) -> SimResult:
    """Simulate len(theta) outbreaks; theta is an nSim x 4 array of posterior draws."""
    n = theta.shape[0]
    mI, mH, epsH = theta[:, 0].copy(), theta[:, 1].copy(), theta[:, 2]
    kappa = 1.0 / theta[:, 3]
    if sc.from_data:                           # index offspring are the data
        mI[:] = 0.0
        mH[:] = 0.0
    z = lambda: np.zeros(n, dtype=np.int64)
    Eu, Et, Iu, It, H, Dd = z(), z(), z(), z(), z(), z()
    cum_cases = np.ones(n, dtype=np.int64)      # index case
    cum_deaths = np.ones(n, dtype=np.int64)     # index case died on day 2
    onsets = np.zeros((n, Tmax + 1), dtype=np.int32)
    active = np.ones(n, dtype=bool)
    TIu, TH = exit_rates(P, P.p, P.gh)
    TIt, _ = exit_rates(P, P.p1, P.gh1)
    rU = [P.p * P.gh, (1 - P.p) * (1 - P.q) * P.gr, (1 - P.p) * P.q * P.gd, P.mu]
    rT = [P.p1 * P.gh1, (1 - P.p1) * (1 - P.q) * P.gr, (1 - P.p1) * P.q * P.gd, P.mu]
    rH = [(1 - P.a) * P.wr, P.a * P.wd, P.mu]
    last_data_onset = int(D.onset_sec.max()) if len(D.onset_sec) else -1

    for t in range(Tmax + 1):
        if not active.any():
            break
        responding = t >= sc.tStar
        if t == sc.tStar:                       # contact tracing begins
            nE = rng.binomial(Eu, sc.fTrace); Eu, Et = Eu - nE, Et + nE
            nI = rng.binomial(Iu, sc.fTrace); Iu, It = Iu - nI, It + nI
        bH = (1 - epsH) * P.betaH if responding else P.betaH
        bD = 0.0 if responding else P.betaD
        new_inf = rng.poisson(P.betaI * (Iu + It) + bH * H + bD * Dd)
        if t <= 2:                              # index case
            new_inf = new_inf + rng.poisson(mI * P.wIdx[t]) + rng.poisson(mH * P.wIdx[t])
        if t == 2 and sc.unsafe_funeral:
            new_inf = new_inf + rng.poisson(P.betaD / P.b, n)
        n_tr = rng.binomial(new_inf, sc.fTrace) if responding else np.zeros(n, dtype=np.int64)
        if sc.from_data:                        # observed cases enter as traced cases
            It = It + int(np.sum(D.onset_sec == t))
        onU, deU = _split(rng, Eu, kappa + P.mu, [kappa, np.full(n, P.mu)])
        onT, deT = _split(rng, Et, kappa + P.mu, [kappa, np.full(n, P.mu)])
        xU = _split(rng, Iu, TIu, [np.full(n, r) for r in rU])
        xT = _split(rng, It, TIt, [np.full(n, r) for r in rT])
        xH = _split(rng, H, TH, [np.full(n, r) for r in rH])
        bur = rng.binomial(Dd, 1 - np.exp(-P.b))
        new = dict(
            Eu=Eu - onU - deU + (new_inf - n_tr),
            Et=Et - onT - deT + n_tr,
            Iu=Iu + onU - sum(xU),
            It=It + onT - sum(xT),
            H=H + xU[0] + xT[0] - sum(xH),
            Dd=Dd + xU[2] + xU[3] + xT[2] + xT[3] + xH[1] + xH[2] - bur)
        n_on = onU + onT
        # apply the day's changes only to simulations still running
        Eu = np.where(active, new["Eu"], Eu); Et = np.where(active, new["Et"], Et)
        Iu = np.where(active, new["Iu"], Iu); It = np.where(active, new["It"], It)
        H = np.where(active, new["H"], H);    Dd = np.where(active, new["Dd"], Dd)
        onsets[:, t] = np.where(active, n_on, 0)
        cum_cases = cum_cases + np.where(active, n_on, 0)
        cum_deaths = cum_deaths + np.where(active, xU[2] + xT[2] + xH[1], 0)
        # stop simulations that exceed the cap or have no infection left
        extinct = (t > 2) & ((Eu + Et + Iu + It + H + Dd) == 0)
        if sc.from_data:
            extinct = extinct & (t > last_data_onset)
        active = active & ~(cum_cases > cap) & ~extinct
    return SimResult(cum_cases, cum_deaths, onsets)


def draw_posterior(post, n, rng):
    return post[rng.integers(0, post.shape[0], n)]


def run_scenarios(post, P: Params, D: ObsData, rng, n_sim=10_000, Tmax=365, cap=5000):
    """Final size and deaths for every scenario."""
    results = {}
    for sc in define_scenarios(P):
        results[sc.name] = simulate(draw_posterior(post, n_sim, rng), P, sc, D, rng, Tmax, cap)
    return results


def end_of_outbreak(post, P: Params, D: ObsData, rng, n_sim=10_000, max_days=60,
                    Tmax=365, cap=5000):
    """Probability that transmission has ended, by days since the last onset.

    The observed secondary cases enter at their onset days as traced cases;
    simulations with no new onset by the end of the data are retained.
    """
    sc = replace(define_scenarios(P)[0], from_data=True)
    res = simulate(draw_posterior(post, n_sim, rng), P, sc, D, rng, Tmax, cap)
    cum_on = np.cumsum(res.onsets, axis=1)                 # onsets up to each day
    total = cum_on[:, -1]
    keep = cum_on[:, D.t_obs] == 0
    cons_cum, cons_total = cum_on[keep], total[keep]
    d_today = D.t_obs - D.last_onset_day
    days_since = np.arange(d_today, max_days + 1)
    p_ended = np.full(days_since.shape, np.nan)
    for k, ds in enumerate(days_since):
        t_cut = min(D.last_onset_day + ds, Tmax)
        none_so_far = cons_cum[:, t_cut] == 0
        if none_so_far.any():
            p_ended[k] = np.mean(cons_total[none_so_far] == cons_cum[none_so_far, t_cut])
    return days_since, p_ended, int(keep.sum())
