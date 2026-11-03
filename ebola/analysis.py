"""Re-estimate everything from a line list as of a given date (the data cut-off).

Used by the watcher after every pass and by the day-by-day replay.
"""
import json
import os

import numpy as np
import pandas as pd

from .data import DAY0, build_data, day_index
from .inference import fit, rc_posterior
from .parameters import Params
from .simulation import end_of_outbreak


def _ci(x):
    q = np.quantile(x, [0.5, 0.025, 0.975])
    return [round(float(v), 3) for v in q]


def update_estimates(linelist: pd.DataFrame, cutoff, n_iter=15_000, n_burn=5_000,
                     n_sim_end=20_000, seed=2026, P: Params = None) -> dict:
    """Fit the model to cases confirmed up to `cutoff` and summarise the results."""
    P = P or Params()
    cutoff = pd.Timestamp(cutoff)
    ll = linelist.copy()
    ll["confirm_date"] = pd.to_datetime(ll["confirm_date"])
    ll["onset_date"] = pd.to_datetime(ll["onset_date"])
    ll = ll[ll["confirm_date"] <= cutoff]
    ll["onset_date"] = ll["onset_date"].fillna(ll["confirm_date"] - pd.Timedelta(days=1))
    D = build_data(ll, cutoff)
    post, _, rhat = fit(D, P, n_iter=n_iter, n_burn=n_burn, seed=seed, verbose=False)
    rc = rc_posterior(post, P)
    sec = ll[ll["role"] == "secondary"]
    res = {
        "cutoff": cutoff.strftime("%Y-%m-%d"),
        "day": int(D.t_obs),
        "cases": int(len(ll)),
        "secondary_household": int((sec["setting"] == "household").sum()),
        "secondary_healthcare": int((sec["setting"] == "healthcare").sum()),
        "deaths": int(((ll["outcome"] == "died") & (
            pd.to_datetime(ll.get("outcome_date", pd.Series(pd.NaT, index=ll.index)),
                           errors="coerce").fillna(ll["confirm_date"]) <= cutoff)).sum()),
        "Rc": _ci(rc),
        "P_Rc_below_1": round(float(np.mean(rc < 1)), 4),
        "incubation_days": _ci(post[:, 3]),
        "index_offspring": _ci(post[:, 0] + post[:, 1]),
        "rhat_max": round(float(np.max(rhat)), 3),
        "contact_alerts": int(((ll["role"] == "secondary") & (ll["listed_contact"] == "no")).sum()),
    }
    if len(sec):                                  # end of outbreak needs a last onset
        days_since, p_end, _ = end_of_outbreak(post, P, D, np.random.default_rng(seed),
                                               n_sim=n_sim_end, max_days=90)
        last_onset = pd.Timestamp(DAY0) + pd.Timedelta(days=D.last_onset_day)
        first = lambda thr: (last_onset + pd.Timedelta(days=int(days_since[np.argmax(p_end >= thr)]))
                             ).strftime("%Y-%m-%d") if np.any(p_end >= thr) else None
        res.update({
            "last_onset": last_onset.strftime("%Y-%m-%d"),
            "days_since_last_onset": int(D.t_obs - D.last_onset_day),
            "P_over_today": round(float(p_end[0]), 3),
            "P_over_at_42_days": round(float(p_end[days_since == 42][0]), 3) if 42 in days_since else None,
            "date_P_over_095": first(0.95),
            "date_P_over_099": first(0.99),
            "curve_days": days_since.tolist(),
            "curve_p": [round(float(v), 4) for v in p_end],
        })
    return res


def save_estimates(res: dict, folder="results", history_name="history.csv", latest=True):
    """Add a row to the history table and, for the live system, write latest.json."""
    os.makedirs(folder, exist_ok=True)
    if latest:
        json.dump(res, open(os.path.join(folder, "latest.json"), "w"), indent=1)
    row = {k: v for k, v in res.items() if not k.startswith("curve")}
    for k in ("Rc", "incubation_days", "index_offspring"):
        row[f"{k}_median"], row[f"{k}_lo"], row[f"{k}_hi"] = row.pop(k)
    path = os.path.join(folder, history_name)
    hist = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    hist = hist[hist.get("cutoff", pd.Series(dtype=str)) != row["cutoff"]] if len(hist) else hist
    pd.concat([hist, pd.DataFrame([row])]).sort_values("cutoff").to_csv(path, index=False)


def backfill_history(linelist: pd.DataFrame, folder="results", history_name="history.csv",
                     log=print, max_days=120):
    """Add an estimate for every past day (from the day after the first confirmation)
    that is missing from the history, using only the cases known on that day."""
    path = os.path.join(folder, history_name)
    have = set(pd.read_csv(path)["cutoff"]) if os.path.exists(path) else set()
    first = pd.to_datetime(linelist["confirm_date"]).min() + pd.Timedelta(days=1)
    yesterday = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
    days = [d for d in pd.date_range(first, yesterday)[-max_days:]
            if d.strftime("%Y-%m-%d") not in have]
    if days:
        log(f"Filling in estimates for {len(days)} past day(s); this takes about "
            f"{max(1, len(days) * 12 // 60)} minute(s), once")
    for d in days:
        save_estimates(update_estimates(linelist, d), folder, history_name, latest=False)
    return len(days)
