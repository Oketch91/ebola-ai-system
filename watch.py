"""Real-time watcher: checks the official sources, extracts new cases with
Claude, and updates the live line list automatically.

In Spyder: set the options below and press F5 (one pass).
To keep watching, run from Anaconda Prompt in this folder:
    python watch.py --loop                (checks every INTERVAL_HOURS)
    python watch.py --test-sources        (checks the sources only, no AI, no cost)

Files (all in data/):
    live_linelist.csv   line list kept up to date by the watcher
    review_queue.json   cases held for a person to check (run review_queue.py)
  and in results/:
    latest.json         latest estimates (Rc, incubation, probability the outbreak is over)
    history.csv         one row of estimates per day
    audit_log_live.csv  every decision, with the supporting sentence
    seen_items.json     reports already processed
    watch_log.txt       what happened on each pass
The verified line list used in the paper (kenya_linelist.csv) is never changed.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime

import pandas as pd

from ebola.analysis import backfill_history, save_estimates, update_estimates
from ebola.extraction import (apply_approved, apply_updates, auto_decide,
                               auto_decide_updates, call_anthropic, extract,
                               fill_descriptions, resolve_deaths)
from ebola.sources import discover, fetch, is_relevant, load_sources

# ---------------------------------------------------------------- options
MODE = "auto"            # "auto": approve only cases that pass every check; hold the rest
                         # "full": approve every case, no human step (problems still logged)
START = "verified"       # first run: start from the verified 9-case line list, or "empty"
COUNTRY = "Kenya"
INTERVAL_HOURS = 3

LIVE = "data/live_linelist.csv"
QUEUE = "data/review_queue.json"
AUDIT = "data/audit_log_live.csv"
SEEN = "data/seen_items.json"
LOG = "data/watch_log.txt"
RESULTS = "results"
CACHE = "data/report_texts.json"           # text of every relevant report read
TOTALS = "data/reported_totals.csv"        # official totals stated in each report


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_json(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def _save_json(obj, path):
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=1, default=str)


def _init_live():
    if not os.path.exists(LIVE):
        src = "data/kenya_linelist.csv" if START == "verified" else "data/replay_linelist_start.csv"
        shutil.copy(src, LIVE)
        log(f"Live line list created from {src}")


def test_sources():
    for src in load_sources():
        try:
            urls = discover(src)
            print(f"OK    {src['name']:<35} {len(urls):3d} items; newest: {urls[-1] if urls else '-'}")
        except Exception as e:
            print(f"FAIL  {src['name']:<35} {type(e).__name__}: {str(e)[:80]}")


def refresh_estimates(force=False):
    """Refit the model if the line list changed or the estimates are not from today.
    (The probability that the outbreak is over changes daily, even with no new case.)"""
    today = datetime.now().strftime("%Y-%m-%d")
    latest = _load_json(os.path.join(RESULTS, "latest.json"), {})
    digest = hashlib.sha256(open(LIVE, "rb").read()).hexdigest()
    if not force and latest.get("cutoff") == today and latest.get("linelist_hash") == digest:
        return latest
    res = update_estimates(pd.read_csv(LIVE), today)
    res["linelist_hash"] = digest
    save_estimates(res, RESULTS)
    msg = (f"Estimates for {today}: {res['cases']} cases; Rc {res['Rc'][0]:.2f} "
           f"({res['Rc'][1]:.2f}-{res['Rc'][2]:.2f}); incubation {res['incubation_days'][0]:.1f} days")
    if "P_over_today" in res:
        msg += (f"; P(outbreak over) {res['P_over_today']:.2f}, "
                f"0.95 on {res['date_P_over_095']}, 0.99 on {res['date_P_over_099']}")
    log(msg)
    if res["Rc"][0] >= 1:
        log("ALERT: median Rc is 1 or above")
    return res


def run_pass(mode=MODE, llm=call_anthropic):
    """One check of every source. Returns the number of cases added."""
    if llm is call_anthropic and not os.environ.get("ANTHROPIC_API_KEY"):
        log("STOPPED: ANTHROPIC_API_KEY is not set in this window. Set it with setx, "
            "then open a NEW Anaconda Prompt (see the instructions).")
        return 0
    _init_live()
    seen = _load_json(SEEN, {})
    queue = [q for q in _load_json(QUEUE, []) if not q.get("death_gap")]   # resolved automatically now
    _save_json(queue, QUEUE)
    cache = _load_json(CACHE, [])
    added = held = n_reports = updated = 0
    for src in load_sources():
        try:
            urls = discover(src)
        except Exception as e:
            log(f"{src['name']}: could not read source ({type(e).__name__})")
            continue
        for url in urls:
            if src["type"] != "single" and url in seen:
                continue
            try:
                item = fetch(url, src["name"], src.get("verify_ssl", True))
            except Exception as e:
                log(f"{src['name']}: could not download {url} ({type(e).__name__})")
                continue
            if seen.get(url) == item.digest:          # unchanged
                continue
            if not is_relevant(item, src):
                seen[url] = item.digest
                _save_json(seen, SEEN)
                continue
            ll = pd.read_csv(LIVE, parse_dates=["confirm_date", "onset_date"])
            try:
                use_pdf = item.kind == "pdf" and not item.text.strip()
                p = extract(item.text or None, None, src["name"], ll, llm=llm,
                            country=COUNTRY, pdf_bytes=item.pdf_bytes if use_pdf else None)
            except Exception as e:                     # leave unseen so it is retried
                log(f"{src['name']}: extraction failed for {url} ({type(e).__name__}: {str(e)[:80]})")
                continue
            n_reports += 1
            decided = auto_decide(p, ll, mode)
            if not decided.empty:
                apply_approved(decided, p, LIVE, AUDIT, "auto", verbose=False)
            upd = auto_decide_updates(p, mode)
            n_upd = apply_updates(upd, p, LIVE, AUDIT, "auto")
            upd_hold = upd[upd["decision"] == "hold"] if not upd.empty else upd
            if len(upd_hold):
                queue.append({"url": url, "source": src["name"], "report_date": p.report_date,
                              "totals": p.totals, "notes": p.notes, "cases": [],
                              "updates": upd_hold.drop(columns="decision").to_dict("records")})
                _save_json(queue, QUEUE)
            # official totals, for the dashboard
            pd.DataFrame([{"report_date": p.report_date, "source": src["name"], "url": url,
                           "cases": p.totals.get("confirmed_cases"), "deaths": p.totals.get("deaths")}]
                         ).to_csv(TOTALS, mode="a", index=False, header=not os.path.exists(TOTALS))
            gap = getattr(p, "death_gap", 0)
            if gap and item.text.strip():
                try:
                    r = resolve_deaths(item.text, cache, pd.read_csv(LIVE), gap, llm=llm)
                    if r["deaths"]:
                        res_upd = pd.DataFrame([{"case_id": d["case_id"], "outcome": "died",
                                                 "outcome_date": d.get("outcome_date") or "",
                                                 "evidence": d.get("evidence", ""), "issues": "",
                                                 "decision": "approve"} for d in r["deaths"]])
                        n_upd += apply_updates(res_upd, p, LIVE, AUDIT, "auto")
                    n_desc = fill_descriptions(r["descriptions"], LIVE)
                    left = gap - len(r["deaths"])
                    log(f"{src['name']}: report states {p.totals.get('deaths')} deaths; "
                        f"{len(r['deaths'])} matched automatically "
                        f"({', '.join(d['case_id'] for d in r['deaths']) or 'none'}), "
                        f"{n_desc} description(s) added"
                        + (f"; {left} death(s) not attributable to a case (shown from official totals)"
                           if left else ""))
                except Exception as e:
                    log(f"{src['name']}: death matching failed ({type(e).__name__}); "
                        "official total still recorded")
            if item.text.strip():
                cache.append({"date": p.report_date, "source": src["name"], "text": item.text[:8000]})
                _save_json(cache, CACHE)
            n_ok = int((decided.get("decision") == "approve").sum()) if not decided.empty else 0
            hold = decided[decided["decision"] == "hold"] if not decided.empty else decided
            if len(hold):
                queue.append({"url": url, "source": src["name"], "report_date": p.report_date,
                              "totals": p.totals, "notes": p.notes,
                              "cases": hold.drop(columns="decision").to_dict("records")})
                _save_json(queue, QUEUE)
                if hold["issues"].str.contains("ALERT").any():
                    log(f"ALERT: {src['name']} {p.report_date} reports a case who was NOT a listed contact")
            added += n_ok
            updated += n_upd
            held += len(hold)
            log(f"{src['name']} {p.report_date}: {len(decided)} new case(s) found, "
                f"{n_ok} added, {len(hold)} held, {n_upd} outcome update(s); "
                f"stated total {p.totals.get('confirmed_cases')}, deaths {p.totals.get('deaths')}")
            seen[url] = item.digest
            _save_json(seen, SEEN)
    n_live = len(pd.read_csv(LIVE))
    log(f"Pass complete: {n_reports} relevant report(s), {added} case(s) added, {held} held, "
        f"{updated} outcome update(s); "
        f"live line list holds {n_live} cases; {len(queue)} report(s) awaiting review")
    refresh_estimates(force=bool(added or updated))
    n_back = backfill_history(pd.read_csv(LIVE), RESULTS, log=log)
    if n_back:
        log(f"History complete: {n_back} past day(s) added")
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--test-sources", action="store_true")
    ap.add_argument("--mode", choices=["auto", "full"], default=MODE)
    ap.add_argument("--interval", type=float, default=INTERVAL_HOURS)
    args = ap.parse_args(sys.argv[1:] if "spyder" not in sys.modules else [])
    if args.test_sources:
        test_sources()
    elif args.loop:
        log(f"Watching every {args.interval} h in {args.mode} mode (Ctrl+C to stop)")
        while True:
            run_pass(args.mode)
            time.sleep(args.interval * 3600)
    else:
        run_pass(args.mode)
