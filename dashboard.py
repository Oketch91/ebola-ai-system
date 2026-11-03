"""Decision dashboard for the AI-assisted real-time Ebola disease outbreak
analytics system.

Normally started by double-clicking "Start Ebola system.bat".
Live view (default):          streamlit run dashboard.py
Retrospective replay:         streamlit run dashboard.py -- --replay
Online, the replay opens with ?view=replay at the end of the app's address.
"""
import json
import os
import sys

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ebola.analysis import update_estimates
from ebola.data import build_data
from ebola.inference import fit
from ebola.parameters import Params
from ebola.simulation import Scenario, simulate
from ebola.sitrep import write_sitrep

st.set_page_config(page_title="Ebola outbreak analytics: Kenya", layout="wide")
P = Params()
DATE_FMT = "%a %d %b %Y"                    # e.g. Tue 03 Nov 2026


def vline1(date, label, color="black"):
    """Vertical dashed line with its label written vertically beside it."""
    df = pd.DataFrame({"d": [pd.Timestamp(date)], "label": [label]})
    rule = alt.Chart(df).mark_rule(color=color, strokeDash=[4, 4]).encode(x="d:T")
    text = alt.Chart(df).mark_text(angle=270, align="right", baseline="bottom", dy=-4,
                                   color=color, fontSize=12).encode(
        x="d:T", y=alt.value(4), text="label:N")
    return rule + text

def vline(date, label, color="black", y=None):
    """Vertical dashed line with its label written vertically beside it.
    y: where to centre the label, in the chart's own units (e.g. 0.5 for a probability);
       if omitted, the label hangs from the top."""
    df = pd.DataFrame({"d": [pd.Timestamp(date)], "label": [label]})
    rule = alt.Chart(df).mark_rule(color=color, strokeDash=[4, 4]).encode(x="d:T")
    text = alt.Chart(df).mark_text(angle=270, align="center" if y is not None else "right",
                                   baseline="bottom", dy=-4, color=color, fontSize=12).encode(
        x="d:T", y=alt.datum(y) if y is not None else alt.value(4), text="label:N")
    return rule + text

# ---------------------------------------------------------------- data
def read_csv(path):
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


@st.cache_data(show_spinner="Fitting the model to the data available on this date...")
def posterior(ll_csv: str, cutoff: str):
    ll = pd.read_csv(pd.io.common.StringIO(ll_csv), parse_dates=["confirm_date", "onset_date"])
    ll = ll[ll["confirm_date"] <= pd.Timestamp(cutoff)].copy()
    ll["onset_date"] = ll["onset_date"].fillna(ll["confirm_date"] - pd.Timedelta(days=1))
    post, _, _ = fit(build_data(ll, cutoff), P, n_iter=15_000, n_burn=5_000, verbose=False)
    return post


@st.cache_data(show_spinner="Simulating outbreaks...")
def run_scenario(ll_csv, cutoff, delay, trace, funeral, n=4000):
    post = posterior(ll_csv, cutoff)
    ll = pd.read_csv(pd.io.common.StringIO(ll_csv), parse_dates=["confirm_date", "onset_date"])
    ll["onset_date"] = ll["onset_date"].fillna(ll["confirm_date"] - pd.Timedelta(days=1))
    D = build_data(ll, cutoff)
    rng = np.random.default_rng(1)
    sc = Scenario("custom", "custom", P.tStar + delay, trace / 100, funeral)
    r = simulate(post[rng.integers(0, len(post), n)], P, sc, D, rng)
    return r.cum_cases, r.cum_deaths


# ---------------------------------------------------------------- sidebar
st.sidebar.title("Ebola outbreak analytics")
st.sidebar.caption("AI-assisted real-time system")
view = ("Replay" if "--replay" in sys.argv
        or str(st.query_params.get("view", "")).lower() == "replay" else "Live")

# Online (Streamlit Community Cloud): the API key and the report password are stored as secrets
try:
    SECRETS = dict(st.secrets)
except Exception:
    SECRETS = {}
if SECRETS.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = SECRETS["ANTHROPIC_API_KEY"]
if view.startswith("Replay"):
    hist = read_csv("results/replay_history.csv")
    ll_all = read_csv("data/replay_linelist.csv")
    curves = json.load(open("results/replay_curves.json")) if os.path.exists("results/replay_curves.json") else {}
    if hist.empty or ll_all.empty:
        st.warning("Run replay.py and then replay_history.py first.")
        st.stop()
    st.warning("RETROSPECTIVE REPLAY of the October 2026 outbreak, for demonstration and "
               "evaluation. This is not current data.")
    asof = st.sidebar.select_slider("Show the situation as on", options=list(hist["cutoff"]),
                                    value=hist["cutoff"].iloc[-1])
    row = hist[hist["cutoff"] == asof].iloc[0].to_dict()
    curve = curves.get(asof)
else:
    hist = read_csv("results/history.csv")
    ll_all = read_csv("data/live_linelist.csv")
    if ll_all.empty:
        ll_all = read_csv("data/kenya_linelist.csv")
    latest = json.load(open("results/latest.json")) if os.path.exists("results/latest.json") else {}
    if hist.empty or latest.get("cutoff") not in set(hist.get("cutoff", [])):
        st.info("Computing live estimates from the line list...")
        from ebola.analysis import save_estimates
        latest = update_estimates(ll_all, pd.Timestamp.today().normalize())
        save_estimates(latest)
        hist = read_csv("results/history.csv")
    asof = latest["cutoff"]
    row = hist[hist["cutoff"] == asof].iloc[0].to_dict()
    curve = (latest.get("curve_days"), latest.get("curve_p")) if "curve_days" in latest else None
if view == "Live":
    _mtime = os.path.getmtime("results/latest.json") if os.path.exists("results/latest.json") else 0

    @st.fragment(run_every=300)                 # check every 5 minutes
    def _auto_refresh():
        if os.path.exists("results/latest.json") and os.path.getmtime("results/latest.json") != _mtime:
            st.rerun(scope="app")
    _auto_refresh()
    st.sidebar.caption("Updates automatically when new reports are processed.")
st.sidebar.markdown(f"**Data up to:** {asof}")
st.sidebar.caption("Model: SEIHDR, Bayesian fit to confirmed cases by setting. "
                   "Transmission rates outside quarantine from the 1995 Kikwit outbreak.")

# ---- Footer at the bottom of the side panel (edit the text below) ----
from datetime import date
FOOTER_TEXT = f"© {date.today().year} USIU-Africa. All rights reserved."
st.sidebar.divider()
st.sidebar.caption(FOOTER_TEXT)

ll_all["confirm_date"] = pd.to_datetime(ll_all["confirm_date"])
ll = ll_all[ll_all["confirm_date"] <= pd.Timestamp(asof)]
ll_csv = ll_all.to_csv(index=False)
num = lambda k: row.get(k) if row.get(k) == row.get(k) else None      # NaN -> None

# ---------------------------------------------------------------- headline
st.title("Ebola disease (Bundibugyo virus) in Kenya")
c = st.columns(5)
c[0].metric("Confirmed cases", int(row["cases"]), help="Including the imported index case")
tot = read_csv("data/reported_totals.csv") if not view.startswith("Replay") else pd.DataFrame()
tot = tot.dropna(subset=["deaths"]) if not tot.empty else tot
if not tot.empty:
    # cumulative totals never fall, so the highest stated total is the most recent
    c[1].metric("Deaths (reported)", int(tot["deaths"].max()),
                help=f"Highest official total stated in any report; "
                     f"{int(row['deaths'])} attributed to cases in the line list")
else:
    c[1].metric("Deaths", int(row["deaths"]), help="Deaths recorded against cases in the line list")
c[2].metric("Rc (control)", f"{row['Rc_median']:.2f}",
            help=f"Control reproduction number; 95% CrI {row['Rc_lo']:.2f}-{row['Rc_hi']:.2f}")
c[3].metric("Incubation (mean)", f"{row['incubation_days_median']:.1f} days",
            help=f"95% CrI {row['incubation_days_lo']:.1f}-{row['incubation_days_hi']:.1f}")
c[4].metric("P(outbreak over)",
            f"{num('P_over_today'):.2f}" if num("P_over_today") is not None else "n/a",
            help="Probability that transmission has ended; needs at least one secondary case")
if (num("contact_alerts") or 0) > 0:
    st.error(f"ALERT: {int(row['contact_alerts'])} case(s) were not on the contact list, "
             "which suggests an unknown chain of transmission.")
if row["Rc_median"] >= 1:
    st.error("ALERT: the median control reproduction number is 1 or above.")
if num("date_P_over_095"):
    st.success(f"If no new case occurs, the probability that transmission has ended reaches "
               f"0.95 on **{row['date_P_over_095']}** and 0.99 on **{row['date_P_over_099']}** "
               f"(the WHO 42-day rule would declare the end on "
               f"{(pd.Timestamp(row['last_onset']) + pd.Timedelta(days=42)).date()}).")
st.caption("Rc is informed by the absence of cases among quarantined contacts, so early "
           "values mostly reflect prior assumptions and become precise as quarantine days pass "
           "without a new case.")

tabs = st.tabs(["Cases", "Estimates over time", "End of outbreak", "Scenarios",
                "AI situation report", "Data and audit"])

with tabs[0]:
    epi = (ll[ll["role"] != "index"].groupby(["confirm_date", "setting"]).size()
           .rename("cases").reset_index())
    idx = ll[ll["role"] == "index"].assign(setting="imported (index)").groupby(
        ["confirm_date", "setting"]).size().rename("cases").reset_index()
    epi = pd.concat([idx, epi])
    if epi.empty:
        st.write("No confirmed case yet.")
    else:
        st.altair_chart(alt.Chart(epi).mark_bar().encode(
            x=alt.X("yearmonthdate(confirm_date):O", title="Date of confirmation"),
            y=alt.Y("cases:Q", title="Confirmed cases"),
            color=alt.Color("setting:N", title="Setting of exposure")), width="stretch")

with tabs[1]:
    h = hist.copy()
    h["cutoff"] = pd.to_datetime(h["cutoff"])
    cols = st.columns(2)
    for col, k, lab in [(cols[0], "Rc", "Control reproduction number Rc"),
                        (cols[1], "incubation_days", "Mean incubation period (days)")]:
        base = alt.Chart(h).encode(x=alt.X("cutoff:T", title="Data up to",
                                           axis=alt.Axis(format="%b %d")))
        band = base.mark_area(opacity=0.25).encode(y=alt.Y(f"{k}_lo:Q", title=lab), y2=f"{k}_hi:Q")
        line = base.mark_line().encode(y=f"{k}_median:Q")
        layers = band + line + vline(asof, pd.Timestamp(asof).strftime(DATE_FMT))
        if k == "Rc":
            layers += alt.Chart(pd.DataFrame({"y": [1]})).mark_rule(color="red").encode(y="y:Q")
        col.altair_chart(layers, width="stretch")
    st.caption("Lines are posterior medians; shaded bands are 95% credible intervals.")

with tabs[2]:
    if curve and curve[0]:
        cdf = pd.DataFrame({"days": curve[0], "p": curve[1]})
        cdf["date"] = pd.Timestamp(row["last_onset"]) + pd.to_timedelta(cdf["days"], unit="D")
        ch = alt.Chart(cdf).mark_line().encode(
            x=alt.X("date:T", title="Date", axis=alt.Axis(format="%b %d")),
            y=alt.Y("p:Q", title="P(transmission has ended)", scale=alt.Scale(domain=[0, 1])))
        d42 = pd.Timestamp(row["last_onset"]) + pd.Timedelta(days=42)
        st.altair_chart(ch + vline(d42, f"WHO 42-day declaration: {d42.strftime(DATE_FMT)}", "red", y=0.5),
                width="stretch")
        st.caption(f"Assumes no new case after {pd.Timestamp(asof).strftime(DATE_FMT)}. "
           f"Last onset {pd.Timestamp(row['last_onset']).strftime(DATE_FMT)}; "
           "red dashed line: earliest date when World Health organization (WHO) would declare the outbreak over "
           "(42 days after the last case, if no new case occurs).")
    else:
        st.write("Available once the first secondary case has been confirmed.")

with tabs[3]:
    st.write("What if the response had been different? Each run simulates 4000 outbreaks "
             "with parameters drawn from the posterior for the selected date.")
    s = st.columns(3)
    delay = s[0].slider("Delay in confirming the index case (days)", 0, 21, 0)
    trace = s[1].slider("Infected contacts found and quarantined (%)", 20, 100, 100, step=10)
    funeral = s[2].toggle("Unsafe funeral of the index case")
    cases, deaths = run_scenario(ll_csv, asof, delay, trace, funeral)
    base_cases, _ = run_scenario(ll_csv, asof, 0, 100, False)
    m = st.columns(4)
    m[0].metric("Median outbreak size", int(np.median(cases)),
                delta=int(np.median(cases) - np.median(base_cases)), delta_color="inverse")
    m[1].metric("95% prediction interval", f"{int(np.quantile(cases, .025))}-{int(np.quantile(cases, .975))}")
    m[2].metric("P(more than 20 cases)", f"{np.mean(cases > 20):.0%}",
                delta=f"{np.mean(cases > 20) - np.mean(base_cases > 20):+.0%}", delta_color="inverse")
    m[3].metric("P(more than 100 cases)", f"{np.mean(cases > 100):.1%}")
    hist_df = pd.DataFrame({"cases": np.minimum(cases, 150)})
    st.altair_chart(alt.Chart(hist_df).mark_bar().encode(
        x=alt.X("cases:Q", bin=alt.Bin(step=5), title="Final number of cases (150 = 150 or more)"),
        y=alt.Y("count()", title="Simulations")), width="stretch")
    st.caption("Deltas compare with the observed response. Simulations include stochastic chance, "
               "so small differences are not meaningful.")

with tabs[4]:
    st.write("Claude writes a plain-language summary using only the numbers above. "
             "Every number in the text is then checked against the model outputs.")
    allowed = True
    if SECRETS.get("SITREP_PASSWORD"):
        pw = st.text_input("Password (to protect the AI service from public use)", type="password")
        allowed = pw == SECRETS["SITREP_PASSWORD"]
        if pw and not allowed:
            st.error("Incorrect password.")
    if st.button("Generate situation report", disabled=not allowed):
        data = {k: v for k, v in row.items() if v == v}
        try:
            text, untraced = write_sitrep(data)
            st.session_state["sitrep"] = (asof, text, untraced)
        except Exception as e:
            st.error(f"Could not reach the AI service: {e}")
    if "sitrep" in st.session_state and st.session_state["sitrep"][0] == asof:
        _, text, untraced = st.session_state["sitrep"]
        st.markdown(text)
        if untraced:
            st.warning("Numbers not found in the model outputs (check before use): " + ", ".join(untraced))
        else:
            st.success("Every number in this report is traceable to the model outputs.")
        st.download_button("Download report", text, file_name=f"sitrep_{asof}.txt")

with tabs[5]:
    st.subheader("Line list")
    st.dataframe(ll.assign(confirm_date=ll["confirm_date"].dt.date), width="stretch", hide_index=True)
    audit = read_csv("data/audit_log.csv" if view.startswith("Replay") else "data/audit_log_live.csv")
    if not audit.empty:
        st.subheader("Audit log: every extraction decision")
        st.dataframe(audit, width="stretch", hide_index=True)
    if not view.startswith("Replay"):
        queue = json.load(open("data/review_queue.json")) if os.path.exists("data/review_queue.json") else []
        st.metric("Reports awaiting review", len(queue))
        if os.path.exists("data/watch_log.txt"):
            st.subheader("Watcher log (latest 30 lines)")
            st.code("".join(open("data/watch_log.txt", encoding="utf-8").readlines()[-30:]))
