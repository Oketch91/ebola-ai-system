"""Likelihood and Bayesian estimation (adaptive random-walk Metropolis).

theta = [mI, mH, epsH, incMean]: the index case's expected household and
health-care offspring, the reduction in hospital transmission after the
response, and the mean incubation period (days).
"""
from dataclasses import dataclass

import numpy as np
from scipy.special import gammainc, gammaln

from .data import ObsData
from .model import control_reproduction
from .parameters import Params, with_incubation

NAMES = ["mI (household offspring of index)", "mH (health-care offspring of index)",
         "epsH (reduction in hospital transmission)", "Mean incubation period (days)"]
LOWER = np.array([0.0, 0.0, 0.0, 4.0])      # uniform priors
UPPER = np.array([30.0, 30.0, 1.0, 21.0])


def gamma_pmf(mean: float, sd: float, nmax: int) -> np.ndarray:
    """Daily probability mass of a gamma distribution, days 0..nmax."""
    k = (mean / sd) ** 2
    th = sd ** 2 / mean
    cdf = gammainc(k, np.arange(nmax + 2) / th)
    pmf = np.diff(cdf)
    return pmf / pmf.sum()


def expected_confirmations(theta, D: ObsData, P: Params):
    """Expected daily confirmations of secondary cases (household, health care)."""
    inc = gamma_pmf(theta[3], P.incSD, 80)
    conf = gamma_pmf(P.confMean, P.confSD, 20)
    c = np.convolve(np.convolve(P.wIdx, inc), conf)[: len(D.days)]
    return theta[0] * c, theta[1] * c


def log_lik(theta, D: ObsData, P: Params) -> float:
    """Poisson log-likelihood of daily confirmations by setting, plus the
    absence of tertiary cases among quarantined secondary cases."""
    mu_hh, mu_hcw = expected_confirmations(theta, D, P)
    m1 = np.maximum(mu_hh, 1e-12)
    m2 = np.maximum(mu_hcw, 1e-12)
    ll = (np.sum(D.y_hh * np.log(m1) - m1 - gammaln(D.y_hh + 1))
          + np.sum(D.y_hcw * np.log(m2) - m2 - gammaln(D.y_hcw + 1)))
    Rc = control_reproduction(with_incubation(P, theta[3]), theta[2])
    F = np.cumsum(np.convolve(gamma_pmf(theta[3], P.incSD, 80),
                              gamma_pmf(P.confMean, P.confSD, 20)))
    lag = np.clip(D.t_obs - D.onset_sec, 0, len(F) - 1)
    return ll - Rc * np.sum(F[lag])                  # log P(no tertiary case)


def _to_theta(z):
    return np.array([np.exp(z[0]), np.exp(z[1]), 1 / (1 + np.exp(-z[2])), np.exp(z[3])])


def _log_post(z, D, P):
    th = _to_theta(z)
    if np.any(th <= LOWER) or np.any(th >= UPPER):
        return -np.inf
    log_jac = z[0] + z[1] + np.log(th[2] * (1 - th[2])) + z[3]
    return log_lik(th, D, P) + log_jac


@dataclass
class Chain:
    samples: np.ndarray
    accept: float


def run_metropolis(theta0, D: ObsData, P: Params, n_iter: int, n_burn: int,
                   rng: np.random.Generator) -> Chain:
    """Adaptive random-walk Metropolis on z = [log mI, log mH, logit epsH, log incMean]."""
    z = np.array([np.log(theta0[0]), np.log(theta0[1]),
                  np.log(theta0[2] / (1 - theta0[2])), np.log(theta0[3])])
    lp = _log_post(z, D, P)
    sd = np.array([0.4, 0.4, 1.0, 0.1])
    samples = np.empty((n_iter, 4))
    n_acc = acc_win = 0
    for it in range(n_burn + n_iter):
        z_new = z + sd * rng.standard_normal(4)
        lp_new = _log_post(z_new, D, P)
        if np.log(rng.random()) < lp_new - lp:
            z, lp = z_new, lp_new
            acc_win += 1
            if it >= n_burn:
                n_acc += 1
        if it < n_burn and (it + 1) % 500 == 0:       # adapt during burn-in
            sd = sd * np.exp(acc_win / 500 - 0.234)
            acc_win = 0
        if it >= n_burn:
            samples[it - n_burn] = _to_theta(z)
    return Chain(samples, n_acc / n_iter)


def gelman_rubin(chains) -> np.ndarray:
    """Potential scale reduction factor for each parameter."""
    X = np.stack([c.samples for c in chains], axis=2)      # n x k x m
    n = X.shape[0]
    B = n * np.var(X.mean(axis=0), axis=1, ddof=1)
    W = np.mean(np.var(X, axis=0, ddof=1), axis=1)
    return np.sqrt(((n - 1) / n * W + B / n) / W)


def fit(D: ObsData, P: Params, n_chains=4, n_iter=50_000, n_burn=10_000,
        seed=2026, verbose=True):
    """Run all chains; return pooled posterior samples, chains and R-hat."""
    rng = np.random.default_rng(seed)
    chains = []
    for c in range(n_chains):
        theta0 = [rng.uniform(2, 8), rng.uniform(2, 8), rng.uniform(0.2, 0.9), rng.uniform(7, 13)]
        chains.append(run_metropolis(theta0, D, P, n_iter, n_burn, rng))
        if verbose:
            print(f"Chain {c + 1}: acceptance rate {chains[-1].accept:.2f}")
    post = np.vstack([c.samples for c in chains])
    return post, chains, gelman_rubin(chains)


def rc_posterior(post, P: Params) -> np.ndarray:
    return np.array([control_reproduction(with_incubation(P, th[3]), th[2]) for th in post])
