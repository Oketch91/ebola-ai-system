"""Automatic evaluation of report-level extraction against the independent
reference dataset (DRC cumulative confirmed cases and deaths, INSP series).

    python evaluate_extraction.py --list          which reports can be evaluated (no AI, no cost)
    python evaluate_extraction.py --limit 10      trial run on 10 reports
    python evaluate_extraction.py                 full run (AI answers are saved, so re-runs are free)

Which reports are evaluated is decided WITHOUT the AI: a report qualifies when
its text contains both the reference's confirmed-case count and its death count
for the same date. The latest such date is the expected answer.
Outputs in evaluation/:
    ai_outputs/<id>.json      the AI's raw answer for each report (with model and prompt fingerprint)
    report_level_results.csv  one row per report: expected and extracted values, verdicts
    summary.txt               accuracy with 95% confidence intervals, overall and by language/source
    to_review.csv             disagreements the script could not explain (for a person to check)
"""
import argparse
import hashlib
import json
import math
import os
import re
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ebola import extraction
from ebola.extraction import DEFAULT_MODEL, extract

CORPUS = "corpus"
OUT = "evaluation"
REF = os.path.join(CORPUS, "reference", "drc_insp_timeseries.csv")
COUNTRY = "Democratic Republic of the Congo (DRC)"
PROMPT_HASH = hashlib.sha256(extraction.SYSTEM_PROMPT.encode()).hexdigest()[:16]
NUM = re.compile(r"(?<![\d.,])\d{1,3}(?:[ ,.\u00a0\u202f]\d{3})+(?![\d])|(?<![\d.,])\d+(?![\d])")


def numbers_in(text):
    """All whole numbers in a text, allowing 6 186 / 6,186 / 6.186 / 6186."""
    return {int(re.sub(r"\D", "", m)) for m in NUM.findall(text)}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def evaluable(index, ref):
    """Reports whose text states a reference (cases, deaths) pair, and the expected date."""
    pairs = {r.date: (int(r.confirmed_cases_cumulative), int(r.confirmed_deaths_cumulative))
             for r in ref.itertuples()}
    rows = []
    for r in index.itertuples():
        path = os.path.join(CORPUS, "text", f"{r.id}.txt")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        if not text.strip():
            continue
        nums = numbers_in(text)
        dates = [d for d, (c, dth) in pairs.items() if c in nums and dth in nums]
        if dates:
            d = max(dates)
            rows.append({"id": r.id, "source": r.source, "language": r.language, "url": r.url,
                         "expected_date": d, "expected_cases": pairs[d][0],
                         "expected_deaths": pairs[d][1], "n_dates_in_text": len(dates)})
    return pd.DataFrame(rows)


def _snippet(text, value, width=160):
    if value in (None, ""):
        return ""
    v = int(value) if str(value).isdigit() else None
    if v is None:
        return ""
    s = f"{v:,}"
    for form in [s.replace(",", " "), s, s.replace(",", "."), s.replace(",", "\u00a0"),
                 s.replace(",", "\u202f"), str(v)]:
        k = text.find(form)
        if k >= 0:
            return " ".join(text[max(0, k - width):k + len(form) + width].split())
    return "(value not found in text)"


def context(text, row, ai_cases, ai_as_of):
    return {"text_near_expected": _snippet(text, row["expected_cases"]),
            "text_near_ai_value": _snippet(text, ai_cases) if ai_cases != row["expected_cases"] else ""}


def ask_ai(row, model):
    path = os.path.join(OUT, "ai_outputs", f"{row['id']}.json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    text = open(os.path.join(CORPUS, "text", f"{row['id']}.txt"), encoding="utf-8", errors="replace").read()
    empty = pd.DataFrame(columns=extraction.COLUMNS)
    for attempt in range(3):
        try:
            p = extract(text, None, row["source"], empty, model=model, country=COUNTRY)
            break
        except Exception as e:
            if attempt == 2:
                out = {"id": row["id"], "error": f"{type(e).__name__}: {str(e)[:200]}",
                       "model": model, "prompt_sha": PROMPT_HASH, "attempts": 3,
                       "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                json.dump(out, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
                return out
            time.sleep(10)
    out = {"id": row["id"], "totals": p.totals, "report_date": p.report_date, "notes": p.notes,
           "model": model, "prompt_sha": PROMPT_HASH,
           "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out


def verdict(ai_value, expected, text_numbers):
    if ai_value is None:
        return "missed"
    try:
        v = int(str(ai_value).replace(",", "").replace(" ", ""))
    except ValueError:
        return "wrong: not a number"
    if v == expected:
        return "correct"
    if v in text_numbers:
        return "differs: value stated in report"      # e.g. a different date or an inconsistent report
    return "wrong: value not in report"


def summarise(res):
    n_fail = (res["cases_verdict"] == "failed: unreadable answer").sum()
    lines = [f"Evaluation run {datetime.now():%Y-%m-%d %H:%M}; model {res['model'].iloc[0]}; "
             f"prompt fingerprint {PROMPT_HASH}",
             f"Reports evaluated: {len(res)} (answers that could not be read after 3 attempts: {n_fail}, "
             f"counted as not correct)", ""]

    def block(df, label):
        out = [f"== {label} (n = {len(df)} reports) =="]
        for fig in ["cases", "deaths"]:
            k = (df[f"{fig}_verdict"] == "correct").sum()
            lenient = df[f"{fig}_verdict"].isin(["correct", "differs: value stated in report"]).sum()
            p, lo, hi = wilson(k, len(df))
            pl, lol, hil = wilson(lenient, len(df))
            out.append(f"  {fig:<6} matches reference: {k}/{len(df)} = {p:.1%} (95% CI {lo:.1%}-{hi:.1%}); "
                       f"matches reference or a value stated in the report: {pl:.1%} ({lol:.1%}-{hil:.1%})")
            out.append("         " + ", ".join(f"{v}: {c}" for v, c in df[f"{fig}_verdict"].value_counts().items()))
        k = (df["as_of_correct"]).sum()
        p, lo, hi = wilson(k, len(df))
        out.append(f"  as-of date correct: {k}/{len(df)} = {p:.1%} ({lo:.1%}-{hi:.1%})")
        return out

    lines += block(res, "All reports")
    for lang, g in res.groupby("language"):
        lines += block(g, f"Language: {lang}")
    for src, g in res.groupby("source"):
        lines += block(g, f"Source: {src}")
    # sensitivity: one report per source per week of the expected date
    wk = res.assign(week=pd.to_datetime(res["expected_date"]).dt.isocalendar().week)
    lines += block(wk.sort_values("id").groupby(["source", "week"]).head(1),
                   "Sensitivity: one report per source per week")
    # bootstrap over reports for both figures together
    rng = np.random.default_rng(2026)
    both = ((res["cases_verdict"] == "correct") & (res["deaths_verdict"] == "correct")).to_numpy()
    boots = [both[rng.integers(0, len(both), len(both))].mean() for _ in range(2000)]
    lines += ["", f"Both figures correct: {both.mean():.1%} (bootstrap 95% CI "
                  f"{np.percentile(boots, 2.5):.1%}-{np.percentile(boots, 97.5):.1%}, 2000 replicates)"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    a = ap.parse_args()
    os.makedirs(os.path.join(OUT, "ai_outputs"), exist_ok=True)
    index = pd.read_csv(os.path.join(CORPUS, "corpus_index.csv"))
    ref = pd.read_csv(REF)
    ev = evaluable(index, ref)
    print(f"{len(ev)} reports state a reference (cases, deaths) pair: "
          + ", ".join(f"{k} {v}" for k, v in ev["language"].value_counts().items()))
    if a.list:
        ev.to_csv(os.path.join(OUT, "evaluable_reports.csv"), index=False)
        print(ev.groupby("source").size().to_string())
        print(f"List saved to {OUT}/evaluable_reports.csv (no AI used)")
        return
    if a.limit:
        ev = ev.sample(min(a.limit, len(ev)), random_state=1)
    rows = []
    for i, row in enumerate(ev.to_dict("records"), 1):
        out = ask_ai(row, a.model)
        text = open(os.path.join(CORPUS, "text", f"{row['id']}.txt"), encoding="utf-8", errors="replace").read()
        if "error" in out:
            print(f"  {i}/{len(ev)} {row['id']}: answer could not be read after 3 attempts ({out['error'][:60]})")
            rows.append({**row, "ai_cases": None, "ai_deaths": None, "ai_as_of": None,
                         "cases_verdict": "failed: unreadable answer", "deaths_verdict": "failed: unreadable answer",
                         "as_of_correct": False, "model": out["model"], "prompt_sha": out["prompt_sha"],
                         **context(text, row, None, None)})
            continue
        nums = numbers_in(text)
        t = out["totals"] or {}
        rows.append({**row, "ai_cases": t.get("confirmed_cases"), "ai_deaths": t.get("deaths"),
                     "ai_as_of": t.get("as_of"),
                     "cases_verdict": verdict(t.get("confirmed_cases"), row["expected_cases"], nums),
                     "deaths_verdict": verdict(t.get("deaths"), row["expected_deaths"], nums),
                     "as_of_correct": str(t.get("as_of")) == row["expected_date"],
                     "model": out["model"], "prompt_sha": out["prompt_sha"],
                     **context(text, row, t.get("confirmed_cases"), t.get("as_of"))})
        print(f"  {i}/{len(ev)} {row['id']} cases {rows[-1]['cases_verdict']}, deaths {rows[-1]['deaths_verdict']}")
    res = pd.DataFrame(rows)
    if res.empty:
        print("No results.")
        return
    if res["prompt_sha"].nunique() > 1:
        print("WARNING: answers come from different versions of the instructions; "
              "delete evaluation/ai_outputs to rerun with one version.")
    res.to_csv(os.path.join(OUT, "report_level_results.csv"), index=False)
    review = res[(res["cases_verdict"] != "correct") | (res["deaths_verdict"] != "correct")
                 | (~res["as_of_correct"])]
    review = review.assign(reviewer_verdict="", reviewer_note="")
    review.to_csv(os.path.join(OUT, "to_review.csv"), index=False, encoding="utf-8-sig")
    s = summarise(res)
    open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8").write(s)
    print("\n" + s + f"\n\n{len(review)} report(s) for a person to check (value or date differs, or failed): "
          f"{OUT}/to_review.csv\nFill in reviewer_verdict for each: 'AI correct', 'AI wrong', or "
          f"'reference does not apply' (e.g. report gives later figures than the reference covers).")


if __name__ == "__main__":
    main()
