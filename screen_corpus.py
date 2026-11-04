"""Prepare the screening sheet for the evaluation (run after build_corpus.py).

    python screen_corpus.py

Writes corpus/screening.csv, one row per report, likely relevant reports first.
For each report it shows how often Ebola / Bundibugyo and each country are
mentioned, flags probable duplicates and doubtful publication dates, and
reports gaps in the numbered series (WHO Disease Outbreak News, WHO AFRO weekly
situation reports). Two annotators then fill in, independently:
    include            yes / no
    reason             if no: not about this outbreak / no case data / duplicate / other
    countries          countries the report gives case data for, e.g. DRC;Uganda
    published_checked  the report's real date (YYYY-MM-DD), read from the document
Running it again keeps any entries already made.
"""
import csv
import difflib
import os
import re
from datetime import date

DIR = "corpus"
COUNTRY_WORDS = {"Kenya": ["kenya"], "Uganda": ["uganda", "ouganda"], "Nigeria": ["nigeria", "nigéria"],
                 "DRC": ["democratic republic of the congo", "drc", "république démocratique du congo",
                         "rdc", "dr congo"]}
TOPIC = re.compile(r"\b(ebola|bundibugyo|bvd)\b", re.I)
MIN_MENTIONS = 8        # WHO AFRO pages mention Ebola about 4 times in menus and sidebars alone


def count(words, text):
    return sum(len(re.findall(r"\b" + re.escape(w) + r"\b", text, re.I)) for w in words)


def norm_title(t):
    t = re.sub(r"\|.*$", "", t or "")                     # drop " | WHO | Regional Office ..."
    return re.sub(r"\W+", " ", t).strip().lower()


rows = list(csv.DictReader(open(os.path.join(DIR, "corpus_index.csv"), encoding="utf-8")))
texts = {r["id"]: open(os.path.join(DIR, "text", f"{r['id']}.txt"), encoding="utf-8",
                       errors="replace").read() for r in rows}
path = os.path.join(DIR, "screening.csv")
old = {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8-sig"))} if os.path.exists(path) else {}

# probable duplicates: same series number, or same title and nearly the same text
dup_of = {}
key = {}
for r in sorted(rows, key=lambda r: r["id"]):
    m = re.search(r"Situation Report (\d+)", r["title"] or "", re.I)
    k = f"sitrep{int(m.group(1))}" if m else None
    if k and k in key:
        dup_of[r["id"]] = key[k]
        continue
    if k:
        key[k] = r["id"]
    for other in [o for o in rows if o["id"] < r["id"] and norm_title(o["title"]) == norm_title(r["title"])
                  and norm_title(r["title"])]:
        a, b = texts[r["id"]][:3000], texts[other["id"]][:3000]
        if a and b and difflib.SequenceMatcher(None, a, b).quick_ratio() > 0.97 \
                and difflib.SequenceMatcher(None, a, b).ratio() > 0.95:
            dup_of[r["id"]] = other["id"]
            break

today = date.today().isoformat()
dates = [r["published"] for r in rows if r["published"]]
common = max(set(dates), key=dates.count) if dates else ""
out = []
for r in rows:
    text = texts[r["id"]]
    n_topic = len(TOPIC.findall(text))
    in_title = bool(TOPIC.search(r["title"] or ""))
    counts = {c: count(w, text) for c, w in COUNTRY_WORDS.items()}
    likely = "likely" if (in_title or n_topic >= MIN_MENTIONS) else "check"
    doubtful = (not r["published"] or r["published"] > today
                or (r["published"] == common and dates.count(common) > 10))
    prev = old.get(r["id"], {})
    out.append({"id": r["id"], "published": r["published"],
                "date_doubtful": "yes" if doubtful else "", "source": r["source"],
                "title": r["title"], "url": r["url"], "pre_screen": likely,
                "possible_duplicate_of": dup_of.get(r["id"], ""),
                "ebola_mentions": n_topic, "ebola_in_title": "yes" if in_title else "no",
                **{f"{c}_mentions": n for c, n in counts.items()},
                "include": prev.get("include", ""), "reason": prev.get("reason", ""),
                "countries": prev.get("countries", ""),
                "published_checked": prev.get("published_checked", "")})

out.sort(key=lambda r: (r["pre_screen"] != "likely", bool(r["possible_duplicate_of"]),
                        -int(r["ebola_mentions"]), r["published"]))
with open(path, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig opens cleanly in Excel
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

n_likely = sum(r["pre_screen"] == "likely" for r in out)
print(f"corpus/screening.csv written: {len(out)} reports; {n_likely} likely relevant, "
      f"{len(out) - n_likely} probably not; {len(dup_of)} possible duplicate(s); "
      f"{sum(r['date_doubtful'] == 'yes' for r in out)} date(s) to check")

# gaps in the numbered series
don = sorted({int(m) for r in rows for m in re.findall(r"DON(\d+)", r["url"])})
if don:
    missing = [n for n in range(602, max(don) + 1) if n not in don]
    print(f"WHO Disease Outbreak News collected: {don}")
    print(f"  numbers not collected (some may be other diseases): {missing}")
sit = sorted({int(m.group(1)) for r in rows
              for m in [re.search(r"Situation Report (\d+)", r["title"] or "", re.I)] if m})
if sit:
    print(f"WHO AFRO weekly situation reports collected: {sit}")
    print(f"  missing: {[n for n in range(1, max(sit) + 1) if n not in sit]} "
          f"(and any published after number {max(sit)})")
