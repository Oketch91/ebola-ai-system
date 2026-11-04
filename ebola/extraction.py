"""AI data extraction: read an outbreak report, propose new case records,
check them, and add approved records to the line list.

The language model only PROPOSES records. Nothing reaches the line list
until an analyst approves it, and every change is written to an audit log.
"""
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .data import DAY0

DEFAULT_MODEL = "claude-haiku-5-5"
SETTINGS = {"household", "healthcare", "community", "imported", "unknown"}
ROLES = {"index", "secondary", "unknown"}
YES_NO = {"yes", "no", "unknown"}
OUTCOMES = {"died", "recovered", ""}
COLUMNS = ["case_id", "role", "setting", "confirm_date", "onset_date",
           "listed_contact", "outcome", "outcome_date", "description", "source"]

SYSTEM_PROMPT = """You extract Ebola disease case records from official outbreak reports \
(Ministry of Health press releases, WHO Disease Outbreak News, ECDC or CDC updates).

Rules:
- Report only cases in the country named in the request. Reports often cover several
  countries; ignore cases in any other country.
- Report only NEW confirmed cases that are not already in the existing line list you are given.
  Reports from different agencies often repeat the same cases; a case that matches an
  existing record by date, setting and description is NOT new.
- Use only what the report states. Never guess. If a value is not stated, use null.
- Resolve relative dates ("yesterday", "on Monday") using the report date.
- confirm_date is the date of laboratory confirmation: the date a sample tested positive
  (for example "a sample collected on 5 October tested positive" gives 5 October). If the
  report only says a case "was confirmed" or "tested positive" today or without a date,
  use the report date. Every case must have a confirm_date.
- onset_date is the date symptoms began ("developed fever", "became ill"); null if not stated.
- setting is where the case was exposed: "household" (relatives or people living with a case),
  "healthcare" (health-care workers infected at work), "community", "imported", or "unknown".
- role is "index" for an imported or first case, "secondary" for a case infected locally, or "unknown".
- listed_contact is "yes" if the case was a known contact or in quarantine before diagnosis,
  "no" if not, "unknown" if not stated.
- evidence is the shortest exact sentence or phrase from the report that supports the record.
- If the report gives a death or recovery of a case ALREADY in the line list, report it under
  outcome_updates with that case's case_id, matched using the description column, the order
  of confirmation ("the third case") and the dates. Only when the match is clear; otherwise
  describe it in notes. outcome_date is the date of death or recovery, null if not stated.
- Also report the cumulative totals for that country exactly as the report states them,
  and the date the report was issued. Use these definitions:
  confirmed_cases: laboratory-confirmed cases; deaths: deaths among confirmed cases;
  suspected_cases: suspected cases (not probable cases); contacts_under_follow_up: contacts
  currently followed; as_of: the date the figures refer to ("as of 11 October"), which may be
  earlier than the report date. If the report gives only new figures for a period and no
  cumulative total, use null.

Reply with JSON only, no other text, in this form:
{"report_date": "YYYY-MM-DD" or null,
 "report_totals": {"confirmed_cases": int or null, "deaths": int or null,
                   "suspected_cases": int or null, "contacts_under_follow_up": int or null,
                   "as_of": "YYYY-MM-DD" or null},
 "new_cases": [{"role": str, "setting": str, "confirm_date": "YYYY-MM-DD" or null,
                "onset_date": "YYYY-MM-DD" or null, "listed_contact": str,
                "outcome": "died" or "recovered" or null,
                "outcome_date": "YYYY-MM-DD" or null,
                "description": "age, sex, relationship or occupation as stated, e.g. '65-year-old woman, relative of the first case'",
                "evidence": str}],
 "outcome_updates": [{"case_id": str, "outcome": "died" or "recovered",
                      "outcome_date": "YYYY-MM-DD" or null, "evidence": str}],
 "notes": str}"""


# ---------------------------------------------------------------- language model
def call_anthropic(system: str, user: str, model: str = DEFAULT_MODEL,
                   pdf_bytes: bytes = None) -> str:
    """Send one request to Claude; the key is read from ANTHROPIC_API_KEY.
    A PDF (including a scanned one) can be attached as pdf_bytes."""
    import base64
    import anthropic
    content = [{"type": "text", "text": user}]
    if pdf_bytes:
        content.insert(0, {"type": "document", "source": {
            "type": "base64", "media_type": "application/pdf",
            "data": base64.standard_b64encode(pdf_bytes).decode()}})
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=2000, system=system,
                                 messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in msg.content if b.type == "text")


def _build_user_prompt(report_text, report_date, source, linelist, country):
    cols = [c for c in ["case_id", "role", "setting", "confirm_date", "onset_date",
                        "outcome", "outcome_date", "description"] if c in linelist.columns]
    existing = linelist[cols].copy()
    for c in ("confirm_date", "onset_date"):
        existing[c] = pd.to_datetime(existing[c]).dt.strftime("%Y-%m-%d")
    body = report_text if report_text else "(see the attached PDF document)"
    return (f"Country: {country}\nReport date: {report_date or 'unknown, take it from the report'}\n"
            f"Source: {source}\n\n"
            f"Existing line list ({len(linelist)} cases):\n{existing.to_csv(index=False)}\n"
            f"Report text:\n<<<\n{body}\n>>>")


def _parse_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------- checks
def _check(case: dict, report_date, linelist: pd.DataFrame, n_new: int, totals: dict):
    """Automatic checks; returns a list of issues for the analyst."""
    issues = []
    rd = pd.Timestamp(report_date)
    if case.get("setting") not in SETTINGS:
        issues.append(f"unknown setting '{case.get('setting')}'")
    if case.get("role") not in ROLES:
        issues.append(f"unknown role '{case.get('role')}'")
    if case.get("listed_contact") not in YES_NO:
        issues.append(f"listed_contact '{case.get('listed_contact')}' not yes/no/unknown")
    cd = pd.to_datetime(case.get("confirm_date"), errors="coerce")
    od = pd.to_datetime(case.get("onset_date"), errors="coerce")
    if pd.isna(cd):
        issues.append("no confirmation date")
    else:
        if cd > rd:
            issues.append("confirmation date after the report date")
        if cd < pd.Timestamp(DAY0):
            issues.append("confirmation date before the index case arrived")
    if not pd.isna(od) and not pd.isna(cd) and od > cd:
        issues.append("onset after confirmation")
    if case.get("listed_contact") == "no" and case.get("role") != "index":
        issues.append("ALERT: case was not a listed contact")
    total = totals.get("confirmed_cases")
    if total is not None and len(linelist) + n_new != total:
        issues.append(f"line list would hold {len(linelist) + n_new} cases but report states {total}")
    return issues


@dataclass
class Proposal:
    report_date: str
    source: str
    totals: dict
    cases: pd.DataFrame          # proposed records with issues and evidence
    notes: str = ""
    updates: pd.DataFrame = None  # proposed outcome updates to existing cases
    raw: str = field(default="", repr=False)


def extract(report_text, report_date, source: str, linelist: pd.DataFrame,
            llm=call_anthropic, model: str = DEFAULT_MODEL, country: str = "Kenya",
            pdf_bytes: bytes = None) -> Proposal:
    """Ask the language model for new cases in a report and check each one.
    report_date may be None, in which case the date stated in the report is used."""
    user = _build_user_prompt(report_text, report_date, source, linelist, country)
    raw = llm(SYSTEM_PROMPT, user, model, pdf_bytes)
    out = _parse_json(raw)
    date_known = bool(report_date or out.get("report_date"))
    report_date = report_date or out.get("report_date") or datetime.now().strftime("%Y-%m-%d")
    totals = out.get("report_totals") or {}
    new = out.get("new_cases") or []
    rows = []
    for c in new:
        c = {k: (v if v is not None else "") for k, v in c.items()}
        c["issues"] = "; ".join(_check(c, report_date, linelist, len(new), totals))
        rows.append(c)
    cols = ["role", "setting", "confirm_date", "onset_date", "listed_contact",
            "outcome", "outcome_date", "evidence", "issues"]
    cases = pd.DataFrame(rows, columns=cols)
    if not new and totals.get("confirmed_cases") not in (None, len(linelist)):
        cases.attrs["warning"] = (f"No new cases extracted, but the report states "
                                  f"{totals['confirmed_cases']} cases and the line list holds {len(linelist)}")
    ups = []
    known = set(linelist["case_id"].astype(str)) if "case_id" in linelist else set()
    n_dead_after = int((linelist.get("outcome") == "died").sum()) + sum(
        1 for c in new if c.get("outcome") == "died")
    for u in out.get("outcome_updates") or []:
        u = {k: (v if v is not None else "") for k, v in u.items()}
        issues = []
        if u.get("case_id") not in known:
            issues.append(f"case_id '{u.get('case_id')}' not in the line list")
        else:
            cur = linelist.loc[linelist["case_id"] == u["case_id"], "outcome"]
            if len(cur) and str(cur.iloc[0]) == u.get("outcome"):
                continue                              # already recorded
        if u.get("outcome") not in ("died", "recovered"):
            issues.append(f"unknown outcome '{u.get('outcome')}'")
        if u.get("outcome") == "died":
            n_dead_after += 1
        u["issues"] = issues
        ups.append(u)
    deaths = totals.get("deaths")
    for u in ups:
        if deaths is not None and n_dead_after != deaths:
            u["issues"].append(f"line list would record {n_dead_after} deaths but report states {deaths}")
        u["issues"] = "; ".join(u["issues"])
    updates = pd.DataFrame(ups, columns=["case_id", "outcome", "outcome_date", "evidence", "issues"])
    death_gap = (int(deaths) - n_dead_after) if deaths is not None else 0
    p = Proposal(report_date, source, totals, cases, notes=out.get("notes", ""), raw=raw, updates=updates)
    p.date_known = date_known
    p.death_gap = max(death_gap, 0)          # deaths stated but not matched to any case
    return p


# ---------------------------------------------------------------- automatic decisions
def auto_decide(p: Proposal, linelist: pd.DataFrame, mode: str = "auto") -> pd.DataFrame:
    """Decide without an analyst.

    mode "auto": approve a report's cases only if every case passes every check
                 AND the line list would then match the total the report states;
                 otherwise hold all of that report's cases for review.
    mode "full": approve every proposed case that has a confirmation date;
                 problems are still logged.
    """
    cases = p.cases.copy()
    if cases.empty:
        return cases.assign(decision=[])
    total = p.totals.get("confirmed_cases")
    reconciles = total is not None and len(linelist) + len(cases) == total
    if mode == "full":
        ok = cases["confirm_date"].astype(str).str.len() > 0
        cases["decision"] = ["approve" if o else "hold" for o in ok]
    elif reconciles and (cases["issues"] == "").all():
        cases["decision"] = "approve"
    else:
        cases["decision"] = "hold"
    return cases


def auto_decide_updates(p: Proposal, mode: str = "auto") -> pd.DataFrame:
    """Outcome updates: approve when they pass every check (auto) or always (full)."""
    u = p.updates.copy() if p.updates is not None else pd.DataFrame()
    if u.empty:
        return u.assign(decision=[])
    u["decision"] = ["approve" if (mode == "full" or not i) else "hold" for i in u["issues"]]
    return u


def apply_updates(updates: pd.DataFrame, p: Proposal, linelist_path: str,
                  audit_path: str, analyst: str) -> int:
    """Record approved deaths or recoveries of existing cases, with an audit entry."""
    if updates is None or updates.empty:
        return 0
    ll = pd.read_csv(linelist_path)
    if "outcome_date" not in ll.columns:
        ll["outcome_date"] = ""
    for c in ("outcome", "outcome_date"):
        ll[c] = ll[c].astype(object)
    stamp = datetime.now().isoformat(timespec="seconds")
    audit, n = [], 0
    for _, u in updates.iterrows():
        if u["decision"] == "approve":
            m = ll["case_id"] == u["case_id"]
            ll.loc[m, "outcome"] = u["outcome"]
            # if the report's own date is unknown, leave the date blank rather than guess
            ll.loc[m, "outcome_date"] = u["outcome_date"] or (
                p.report_date if getattr(p, "date_known", True) else "")
            n += 1
        audit.append({"timestamp": stamp, "analyst": analyst, "report_date": p.report_date,
                      "source": p.source, "decision": f"{u['decision']} update",
                      "case_id": u["case_id"], "confirm_date": "", "setting": f"outcome: {u['outcome']}",
                      "evidence": u["evidence"], "issues": u["issues"]})
    if n:
        shutil.copy(linelist_path, linelist_path.replace(".csv", "_backup.csv"))
        ll.to_csv(linelist_path, index=False)
    pd.DataFrame(audit).to_csv(audit_path, mode="a", index=False,
                               header=not os.path.exists(audit_path))
    return n


RESOLVE_PROMPT = """Some deaths stated in the latest outbreak report cannot be matched to a case
in the line list. Using the latest report and the earlier reports, identify which case(s) in the
line list died. Earlier reports often describe each case when it was confirmed (age, sex,
relationship, occupation, confirmation date); use these details and the order of confirmation.
Only name a case when the reports make the match clear. Also give a short description for every
case in the line list whose description is blank, if the reports state one.

Reply with JSON only:
{"deaths": [{"case_id": str, "outcome_date": "YYYY-MM-DD" or null, "evidence": str}],
 "descriptions": {"K02": "39-year-old man, close family member of the first case"}}"""


def resolve_deaths(report_text: str, earlier: list, linelist: pd.DataFrame, n_missing: int,
                   llm=call_anthropic, model: str = DEFAULT_MODEL) -> dict:
    """Ask Claude which existing case(s) account for deaths it could not match the first time."""
    cols = [c for c in ["case_id", "role", "setting", "confirm_date", "outcome", "outcome_date",
                        "description"] if c in linelist.columns]
    past = "\n\n".join(f"--- Earlier report ({e['date']}, {e['source']}) ---\n{e['text'][:4000]}"
                        for e in earlier[-15:])
    user = (f"Unmatched deaths: {n_missing}\n\nLine list:\n{linelist[cols].to_csv(index=False)}\n"
            f"--- Latest report ---\n{report_text[:6000]}\n\n{past}")
    out = _parse_json(llm(RESOLVE_PROMPT, user, model, None))
    known = set(linelist["case_id"].astype(str))
    alive = set(linelist.loc[linelist["outcome"].astype(str) != "died", "case_id"].astype(str))
    deaths = [d for d in out.get("deaths") or [] if d.get("case_id") in alive][:n_missing]
    descr = {k: v for k, v in (out.get("descriptions") or {}).items() if k in known and v}
    return {"deaths": deaths, "descriptions": descr}


def fill_descriptions(descr: dict, linelist_path: str) -> int:
    """Add descriptions to cases that have none."""
    if not descr:
        return 0
    ll = pd.read_csv(linelist_path)
    if "description" not in ll.columns:
        ll["description"] = ""
    ll["description"] = ll["description"].astype(object)
    n = 0
    for cid, d in descr.items():
        m = (ll["case_id"] == cid) & (ll["description"].isna() | (ll["description"].astype(str) == ""))
        if m.any():
            ll.loc[m, "description"] = d
            n += 1
    if n:
        ll.to_csv(linelist_path, index=False)
    return n


# ---------------------------------------------------------------- analyst review
def review_in_console(p: Proposal) -> pd.DataFrame:
    """Show each proposed record and ask the analyst to approve, edit or reject it."""
    print(f"\nReport {p.report_date} ({p.source}); stated totals: {p.totals}")
    if p.notes:
        print(f"Model notes: {p.notes}")
    if "warning" in p.cases.attrs:
        print(f"WARNING: {p.cases.attrs['warning']}")
    if p.cases.empty:
        print("No new cases proposed.")
        return p.cases.assign(decision=[])
    decisions = []
    for i, c in p.cases.iterrows():
        while True:
            print(f"\nProposed case {i + 1} of {len(p.cases)}")
            for k in ["role", "setting", "confirm_date", "onset_date", "listed_contact", "outcome"]:
                print(f"  {k:<15} {c[k]}")
            print(f"  evidence        \"{c['evidence']}\"")
            if c["issues"]:
                print(f"  ISSUES          {c['issues']}")
            ans = input("  [a]pprove, [r]eject, or edit as field=value: ").strip()
            if ans.lower() == "a" and not str(c["confirm_date"]).strip():
                print("  A case needs a confirmation date before it can be approved;"
                      " enter it as confirm_date=YYYY-MM-DD")
                continue
            if ans.lower() in ("a", "r"):
                decisions.append("approve" if ans.lower() == "a" else "reject")
                break
            if "=" in ans:
                k, v = (s.strip() for s in ans.split("=", 1))
                if k in c.index and k not in ("evidence", "issues"):
                    c[k] = v
                    p.cases.loc[i, k] = v
                else:
                    print(f"  '{k}' cannot be edited")
    return p.cases.assign(decision=decisions)


def apply_approved(reviewed: pd.DataFrame, p: Proposal, linelist_path: str,
                   audit_path: str, analyst: str, verbose: bool = True) -> pd.DataFrame:
    """Add approved records to the line list (after a backup) and log every decision."""
    ll = pd.read_csv(linelist_path)
    for col in ("outcome_date", "description"):
        if col not in ll.columns:
            ll[col] = ""
    shutil.copy(linelist_path, linelist_path.replace(".csv", "_backup.csv"))
    n0 = len(ll)
    audit = []
    stamp = datetime.now().isoformat(timespec="seconds")
    for _, c in reviewed.iterrows():
        case_id = ""
        if c["decision"] == "approve":
            case_id = f"K{len(ll) + 1:02d}"
            ll.loc[len(ll)] = {"case_id": case_id, "role": c["role"], "setting": c["setting"],
                               "confirm_date": c["confirm_date"], "onset_date": c["onset_date"],
                               "listed_contact": c["listed_contact"], "outcome": c["outcome"],
                               "description": c.get("description", ""),
                               "outcome_date": c.get("outcome_date", "") or (
                                   p.report_date if c["outcome"] else ""),
                               "source": f"{p.source} {p.report_date}"
                                         + (" [auto]" if analyst == "auto" else "")}
        audit.append({"timestamp": stamp, "analyst": analyst, "report_date": p.report_date,
                      "source": p.source, "decision": c["decision"], "case_id": case_id,
                      "confirm_date": c["confirm_date"], "setting": c["setting"],
                      "evidence": c["evidence"], "issues": c["issues"]})
    ll.to_csv(linelist_path, index=False)
    if audit:
        pd.DataFrame(audit).to_csv(audit_path, mode="a", index=False,
                                   header=not os.path.exists(audit_path))
    if verbose:
        print(f"Line list: {n0} -> {len(ll)} cases ({linelist_path})")
    return ll
