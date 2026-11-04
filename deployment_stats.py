"""Figures on the live deployment, read from the public GitHub repository
(no local files needed).

    python deployment_stats.py [--until YYYY-MM-DD]

Prints and saves evaluation/deployment_stats.txt: period of operation, number
of automatic passes and the interval between them, reports read, cases added
or held, outcome updates, sources that could not be read, and the latest
estimates.
"""
import argparse
import io
import os
import re

import pandas as pd
import requests

REPO = "https://raw.githubusercontent.com/Oketch91/ebola-ai-system/main/"


def get(path):
    r = requests.get(REPO + path, timeout=30)
    return r.text if r.ok else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default=None)
    a = ap.parse_args()
    log = [l.strip() for l in get("data/watch_log.txt").splitlines() if l.strip()]
    rows = []
    for l in log:
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d) (.*)", l)
        if m:
            rows.append((pd.Timestamp(m.group(1)), m.group(2)))
    df = pd.DataFrame(rows, columns=["time", "msg"])
    if a.until:
        df = df[df["time"] < pd.Timestamp(a.until) + pd.Timedelta(days=1)]
    passes = df[df["msg"].str.startswith("Pass complete")].sort_values("time")
    num = lambda pat: passes["msg"].str.extract(pat)[0].astype(float).sum()
    gaps = passes["time"].diff().dropna().dt.total_seconds() / 3600
    unread = df[df["msg"].str.contains("could not read source|could not download|extraction failed")]
    alerts = df[df["msg"].str.contains("ALERT")]
    hist = pd.read_csv(io.StringIO(get("results/history.csv"))) if get("results/history.csv") else pd.DataFrame()
    out = [f"Live deployment: {df['time'].min():%Y-%m-%d %H:%M} to {df['time'].max():%Y-%m-%d %H:%M} "
           f"({(df['time'].max() - df['time'].min()).total_seconds() / 86400:.1f} days)",
           f"Automatic passes: {len(passes)}; interval between passes: median {gaps.median():.1f} h "
           f"(range {gaps.min():.1f}-{gaps.max():.1f} h; scheduled every 3 h)",
           f"Relevant reports read: {int(num(r'(\d+) relevant report'))}; cases added automatically: "
           f"{int(num(r'(\d+) case\(s\) added'))}; cases held for review: {int(num(r'(\d+) held'))}; "
           f"outcome updates: {int(num(r'(\d+) outcome update'))}",
           f"Sources or reports that could not be read on a pass: {len(unread)} "
           f"({'; '.join(unread['msg'].str.slice(0, 70).unique()[:5])})",
           f"Alerts raised: {len(alerts)}"]
    if not hist.empty:
        h = hist.iloc[-1]
        out.append(f"Latest estimates ({h['cutoff']}): {int(h['cases'])} cases, {int(h['deaths'])} deaths; "
                   f"Rc {h['Rc_median']:.2f} ({h['Rc_lo']:.2f}-{h['Rc_hi']:.2f}); "
                   f"P(outbreak over) {h['P_over_today']:.2f}; daily estimates on record: {len(hist)}")
    text = "\n".join(out)
    os.makedirs("evaluation", exist_ok=True)
    open(os.path.join("evaluation", "deployment_stats.txt"), "w", encoding="utf-8").write(text)
    print(text)


if __name__ == "__main__":
    main()
