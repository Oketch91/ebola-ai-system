"""Turn the case line list into the inputs the model needs."""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

DAY0 = date(2026, 10, 3)          # arrival of the index case in Kenya


@dataclass
class ObsData:
    days: np.ndarray               # 0..t_obs
    y_hh: np.ndarray               # daily confirmations, household contacts
    y_hcw: np.ndarray              # daily confirmations, health-care workers
    onset_sec: np.ndarray          # onset day of each secondary case
    last_case_day: int
    last_onset_day: int
    t_obs: int                     # last day of data
    linelist: pd.DataFrame


def day_index(d) -> int:
    """Days since DAY0."""
    return (pd.Timestamp(d).date() - DAY0).days


def load_line_list(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["confirm_date", "onset_date"])
    # Where onset is not reported, assume one day before confirmation
    df["onset_reported"] = df["onset_date"].notna()
    df["onset_date"] = df["onset_date"].fillna(df["confirm_date"] - pd.Timedelta(days=1))
    return df


def build_data(linelist: pd.DataFrame, data_cutoff) -> ObsData:
    t_obs = day_index(data_cutoff)
    sec = linelist[linelist["role"] == "secondary"]
    conf = np.array([day_index(d) for d in sec["confirm_date"]], dtype=int)
    onset = np.sort(np.array([day_index(d) for d in sec["onset_date"]], dtype=int))
    is_hh = (sec["setting"] == "household").to_numpy()
    is_hcw = (sec["setting"] == "healthcare").to_numpy()
    y_hh = np.bincount(conf[is_hh], minlength=t_obs + 1)[: t_obs + 1]
    y_hcw = np.bincount(conf[is_hcw], minlength=t_obs + 1)[: t_obs + 1]
    return ObsData(days=np.arange(t_obs + 1), y_hh=y_hh.astype(float),
                   y_hcw=y_hcw.astype(float), onset_sec=onset,
                   last_case_day=int(conf.max()) if len(conf) else -1,
                   last_onset_day=int(onset.max()) if len(onset) else -1,
                   t_obs=t_obs, linelist=linelist)
