"""Model parameters (Table 1 of the manuscript). Rates are per day."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Params:
    # Demography
    N0: float = 47_564_296              # Kenya, 2019 census (KNBS)
    mu: float = 1 / (63.6 * 365)        # life expectancy 63.6 years (World Bank)
    # Transmission outside quarantine (Legrand et al. 2007, Kikwit 1995, per day)
    betaI: float = 0.588 / 7
    betaH: float = 0.794 / 7
    betaD: float = 7.653 / 7
    # Natural history and outcomes
    kappa: float = 1 / 8.5              # 1 / mean incubation (estimated in the MCMC)
    incSD: float = 4.0                  # incubation SD (days)
    p: float = 0.8                      # weight on hospitalisation, pre-response
    q: float = 0.31                     # weight on death, not hospitalised
    a: float = 0.25                     # weight on death, hospitalised
    gh: float = 1 / 5                   # onset to hospitalisation, pre-response
    gr: float = 1 / 13.0                # onset to recovery
    gd: float = 1 / 9.3                 # onset to death
    wr: float = 1 / 8.0                 # hospitalisation to recovery
    wd: float = 1 / 4.3                 # hospitalisation to death
    b: float = 1 / 2                    # death to burial
    # Response (from 6 October 2026, day 3)
    tStar: int = 3
    p1: float = 1.0                     # all cases identified in quarantine
    gh1: float = 1 / 0.5                # onset to isolation in quarantine
    epsH_default: float = 0.9           # illustrative only
    # Index case
    tauIdx: float = 2.9                 # infectious days in Kenya
    wIdx: tuple = (1 / 2.9, 1 / 2.9, 0.9 / 2.9)   # share of exposure, days 0-2
    confMean: float = 1.5               # onset to confirmation (days)
    confSD: float = 1.0

    @property
    def Lambda(self) -> float:
        """Births per day; keeps the population constant without disease."""
        return self.mu * self.N0


def with_incubation(P: Params, inc_mean: float) -> Params:
    """Copy of P with mean incubation period inc_mean (days)."""
    return replace(P, kappa=1 / inc_mean)
