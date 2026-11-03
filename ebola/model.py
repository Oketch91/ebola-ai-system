"""Deterministic SEIHDR model and its analytical results."""
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from .parameters import Params


def exit_rates(P: Params, p: float, gh: float):
    """Total exit rates from I and H (T_I, T_H)."""
    TI = p * gh + (1 - p) * (1 - P.q) * P.gr + (1 - p) * P.q * P.gd + P.mu
    TH = (1 - P.a) * P.wr + P.a * P.wd + P.mu
    return TI, TH


def seihdr_rhs(t, y, P: Params, post_response: bool = False):
    """Right-hand side of the SEIHDR equations. y = [S, E, I, H, D, R]."""
    S, E, I, H, D, R = y
    N = S + E + I + H + R
    p, gh = (P.p1, P.gh1) if post_response else (P.p, P.gh)
    TI, TH = exit_rates(P, p, gh)
    lam = (P.betaI * I + P.betaH * H + P.betaD * D) / N
    return [P.Lambda - lam * S - P.mu * S,
            lam * S - (P.kappa + P.mu) * E,
            P.kappa * E - TI * I,
            p * gh * I - TH * H,
            (P.mu + (1 - p) * P.q * P.gd) * I + (P.mu + P.a * P.wd) * H - P.b * D,
            (1 - p) * (1 - P.q) * P.gr * I + (1 - P.a) * P.wr * H - P.mu * R]


def next_generation(P: Params):
    """F and V matrices at the disease-free equilibrium, compartments (E, I, H, D)."""
    TI, TH = exit_rates(P, P.p, P.gh)
    F = np.zeros((4, 4))
    F[0, 1:] = [P.betaI, P.betaH, P.betaD]
    V = np.array([[P.kappa + P.mu, 0, 0, 0],
                  [-P.kappa, TI, 0, 0],
                  [0, -P.p * P.gh, TH, 0],
                  [0, -(P.mu + (1 - P.p) * P.q * P.gd), -(P.mu + P.a * P.wd), P.b]])
    return F, V


def early_growth(P: Params) -> float:
    """Early exponential growth rate: largest eigenvalue of F - V."""
    F, V = next_generation(P)
    return float(np.max(np.real(np.linalg.eigvals(F - V))))


@dataclass
class Analytics:
    R0: float
    RI: float
    RH: float
    RD: float
    R0_ngm: float
    Rc: float
    CFR_I: float
    CFR_H: float
    CFR: float
    IFR: float
    DFE: np.ndarray
    EE: np.ndarray


def analytics(P: Params, epsH: float) -> Analytics:
    """R0 and its components, Rc, severity measures and equilibria."""
    TI, TH = exit_rates(P, P.p, P.gh)
    s = P.kappa / (P.kappa + P.mu)
    RI = s * P.betaI / TI
    RH = s * (P.p * P.gh / TI) * P.betaH / TH
    RD = s * (P.betaD / P.b) * ((P.mu + (1 - P.p) * P.q * P.gd) / TI
                                + (P.p * P.gh / TI) * (P.mu + P.a * P.wd) / TH)
    R0 = RI + RH + RD
    F, V = next_generation(P)
    R0_ngm = float(np.max(np.abs(np.linalg.eigvals(F @ np.linalg.inv(V)))))
    TI1, _ = exit_rates(P, P.p1, P.gh1)
    Rc = s * (P.betaI / TI1 + (P.p1 * P.gh1 / TI1) * (1 - epsH) * P.betaH / TH)
    CFR_I = P.q * P.gd / (P.q * P.gd + (1 - P.q) * P.gr)
    CFR_H = P.a * P.wd / (P.a * P.wd + (1 - P.a) * P.wr)
    CFR = (1 - P.p) * P.q * P.gd / TI + (P.p * P.gh / TI) * (P.a * P.wd / TH)
    DFE = np.array([P.Lambda / P.mu, 0, 0, 0, 0, 0])
    EE = np.full(6, np.nan)
    if R0 > 1:
        m = (1 / (P.kappa + P.mu)) * (1 + (P.kappa / TI) * (
            1 + P.p * P.gh / TH + (1 - P.p) * (1 - P.q) * P.gr / P.mu
            + P.p * P.gh * (1 - P.a) * P.wr / (P.mu * TH)))
        lamS = (R0 - 1) / m
        S = P.Lambda / (lamS + P.mu)
        E = lamS * S / (P.kappa + P.mu)
        I = P.kappa * E / TI
        H = P.p * P.gh * I / TH
        D = ((P.mu + (1 - P.p) * P.q * P.gd) * I + (P.mu + P.a * P.wd) * H) / P.b
        R = ((1 - P.p) * (1 - P.q) * P.gr * I + (1 - P.a) * P.wr * H) / P.mu
        EE = np.array([S, E, I, H, D, R])
    return Analytics(R0, RI, RH, RD, R0_ngm, Rc, CFR_I, CFR_H, CFR, s * CFR, DFE, EE)


def run_deterministic(P: Params, t_end: float = 150):
    """Trajectory without a response, from one infectious case."""
    y0 = [P.N0 - 1, 0, 1, 0, 0, 0]
    t_eval = np.linspace(0, t_end, int(t_end) * 4 + 1)
    sol = solve_ivp(seihdr_rhs, (0, t_end), y0, args=(P, False), method="RK45",
                    t_eval=t_eval, rtol=1e-8, atol=1e-6)
    return sol.t, sol.y


def control_reproduction(P: Params, epsH: float) -> float:
    """Control reproduction number Rc (fast version of analytics(P, epsH).Rc)."""
    _, TH = exit_rates(P, P.p, P.gh)
    TI1, _ = exit_rates(P, P.p1, P.gh1)
    s = P.kappa / (P.kappa + P.mu)
    return s * (P.betaI / TI1 + (P.p1 * P.gh1 / TI1) * (1 - epsH) * P.betaH / TH)
