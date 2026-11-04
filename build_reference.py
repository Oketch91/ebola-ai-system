"""Download the independent reference dataset for the evaluation and add the
reports it is based on to the collection.

    python build_reference.py

Reference: curated time series of cumulative confirmed cases and deaths among
confirmed cases in the DRC, compiled from the official INSP/COUSP situation
reports by Pacès and Liegertová (Institute of Molecular Genetics, Czech Academy
of Sciences), CC BY 4.0: https://titan.img.cas.cz/ebola/en/graf-vyvoj.html

Saves  corpus/reference/drc_insp_timeseries.csv   (unchanged copy)
       corpus/reference/REFERENCE_INFO.json       (address, download time, fingerprint)
and adds every INSP situation report it cites to corpus/manual_reports.csv,
so that build_corpus.py collects them (including the linked PDF).
Then run:  python build_corpus.py   and   python screen_corpus.py
"""
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone

from ebola.sources import http_get

URL = "https://titan.img.cas.cz/ebola/data/drc-bdbv-sitrep-timeseries.csv"
DIR = os.path.join("corpus", "reference")
MANUAL = os.path.join("corpus", "manual_reports.csv")
SOURCE = "DRC INSP situation reports"

os.makedirs(DIR, exist_ok=True)
raw = http_get(URL).content
open(os.path.join(DIR, "drc_insp_timeseries.csv"), "wb").write(raw)
rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
info = {"url": URL, "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(raw).hexdigest(), "rows": len(rows),
        "first_date": min(r["date"] for r in rows), "last_date": max(r["date"] for r in rows),
        "licence": "CC BY 4.0",
        "citation": "Pačes J, Liegertová M. Ebola caused by Bundibugyo virus, 2026: case and death "
                    "trajectory chart. Institute of Molecular Genetics of the Czech Academy of Sciences."}
json.dump(info, open(os.path.join(DIR, "REFERENCE_INFO.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"Reference saved: {len(rows)} days, {info['first_date']} to {info['last_date']}")

manual = list(csv.DictReader(open(MANUAL, encoding="utf-8")))
have = {r["url"] for r in manual}
added = 0
for r in rows:
    u = r["source_url"].strip()
    if u and u not in have:
        manual.append({"url": u, "source": SOURCE,
                       "note": f"INSP SitRep {r['sitrep_number']}, data as of {r['source_data_as_of_date']}"})
        have.add(u)
        added += 1
with open(MANUAL, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["url", "source", "note"])
    w.writeheader()
    w.writerows(manual)
print(f"{added} INSP situation report(s) added to {MANUAL}; now run: python build_corpus.py")
