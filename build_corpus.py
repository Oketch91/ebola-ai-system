"""Step 2 of the evaluation: collect and archive every official report.

Run once in Anaconda Prompt, in the project folder:
    python build_corpus.py

It finds reports from the sources in corpus/sources_corpus.json, adds any
addresses listed by hand in corpus/manual_reports.csv (for example ministry
press releases or weekly situation reports), keeps those about Ebola disease
in Kenya, Uganda, Nigeria or the DRC from 15 May 2026 onwards, and saves for
each one:
    corpus/archive/<id>.html or .pdf   the original document, unchanged
    corpus/text/<id>.txt               its text
    corpus/corpus_index.csv            one row per report: address, source,
                                       publication date, language, countries
                                       mentioned, SHA-256 fingerprint
Running it again adds only new reports. When the team decides to freeze the
collection, run:  python build_corpus.py --freeze
"""
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ebola.sources import _pdf_text, discover, fetch, http_get

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False

SOURCE_COUNTRY = {"DRC INSP situation reports": "DRC"}   # sources that only report on one country

START_DATE = "2026-05-15"                   # declaration of the outbreak
COUNTRIES = {"Kenya": ["kenya"], "Uganda": ["uganda", "ouganda"],
             "Nigeria": ["nigeria", "nigéria"],
             "DRC": ["democratic republic of the congo", "drc", "république démocratique du congo",
                     "rdc", "dr congo"]}
TOPIC = ["ebola", "bundibugyo", "mvb", "mvebdb", "maladie à virus"]
FRENCH_WORDS = [" le ", " la ", " les ", " des ", " est ", " dans ", " cas ", " une ", " pour "]
ENGLISH_WORDS = [" the ", " and ", " of ", " cases ", " is ", " in ", " with ", " for "]

DIR = "corpus"
INDEX = os.path.join(DIR, "corpus_index.csv")
FIELDS = ["id", "url", "source", "title", "published", "retrieved", "language",
          "countries", "kind", "sha256", "n_chars", "manual_note"]


def language(text):
    t = " " + text.lower() + " "
    fr = sum(t.count(w) for w in FRENCH_WORDS)
    en = sum(t.count(w) for w in ENGLISH_WORDS)
    return "fr" if fr > en else "en"


def countries_in(text, source=""):
    t = text.lower()
    found = [c for c, words in COUNTRIES.items()
             if any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words)]
    if source in SOURCE_COUNTRY and SOURCE_COUNTRY[source] not in found:
        found.append(SOURCE_COUNTRY[source])
    return found


def refresh_pdf_text(rows):
    """Re-read the text of saved PDFs that were stored without text (no new download)."""
    n = 0
    for r in rows:
        if r["kind"] == "pdf" and int(r["n_chars"] or 0) == 0:
            path = os.path.join(DIR, "archive", f"{r['id']}.pdf")
            if not os.path.exists(path):
                continue
            text = _pdf_text(open(path, "rb").read())
            if text.strip():
                open(os.path.join(DIR, "text", f"{r['id']}.txt"), "w", encoding="utf-8").write(text)
                r["n_chars"] = len(text)
                r["language"] = language(text)
                r["countries"] = ";".join(countries_in(text, r["source"]))
                if not r["published"]:
                    r["published"] = published_date(b"", text)[0]
                n += 1
    return n


def published_date(raw: bytes, text: str):
    """(date, from_metadata): the publication date from the page's metadata if present,
    otherwise the first date in the text, which may be an earlier event date."""
    try:
        soup = BeautifulSoup(raw, "html.parser")
        for key in ["article:published_time", "og:updated_time", "dcterms.date", "date"]:
            tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
            if tag and tag.get("content"):
                m = re.search(r"\d{4}-\d{2}-\d{2}", tag["content"])
                if m:
                    return m.group(0), True
        t = soup.find("time")
        if t and t.get("datetime"):
            return t["datetime"][:10], True
    except Exception:
        pass
    months = ("January|February|March|April|May|June|July|August|September|October|"
              "November|December|janvier|février|mars|avril|mai|juin|juillet|août|"
              "septembre|octobre|novembre|décembre")
    m = re.search(rf"\b(\d{{1,2}}) ({months}) (2026)\b", text, re.I)
    if m:
        fr = {"janvier": "January", "février": "February", "mars": "March", "avril": "April",
              "mai": "May", "juin": "June", "juillet": "July", "août": "August",
              "septembre": "September", "octobre": "October", "novembre": "November",
              "décembre": "December"}
        month = fr.get(m.group(2).lower(), m.group(2))
        try:
            return datetime.strptime(f"{m.group(1)} {month} 2026", "%d %B %Y").strftime("%Y-%m-%d"), False
        except ValueError:
            pass
    return "", False


def load_index():
    if not os.path.exists(INDEX):
        return []
    return list(csv.DictReader(open(INDEX, encoding="utf-8")))


def save_index(rows):
    with open(INDEX, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["published"] or "9999", r["id"])))


FOLLOW = {}          # source name -> pattern of linked documents to collect as well


def candidates():
    """(url, source, note) for every report the sources currently list."""
    out = []
    for src in json.load(open(os.path.join(DIR, "sources_corpus.json"), encoding="utf-8")):
        try:
            urls = discover(src, max_items=src.get("max_items", 200))
            if src.get("follow_pattern"):
                FOLLOW[src["name"]] = src["follow_pattern"]
            print(f"OK    {src['name']:<40} {len(urls):4d} items")
            out += [(u, src["name"], "") for u in urls]
        except Exception as e:
            print(f"FAIL  {src['name']:<40} {type(e).__name__}")
    manual = os.path.join(DIR, "manual_reports.csv")
    if os.path.exists(manual):
        rows = list(csv.DictReader(open(manual, encoding="utf-8")))
        FOLLOW.setdefault("WHO AFRO situation reports", r"iris\.who\.int/bitstreams/[^/]+/download")
        FOLLOW.setdefault("DRC INSP situation reports", r"insp\.cd/wp-content/uploads/.+\.pdf")
        print(f"OK    {'Manual list':<40} {len(rows):4d} items")
        out += [(r["url"], r["source"], r.get("note", "")) for r in rows if r.get("url")]
    return out


def main():
    if "--freeze" in sys.argv:
        rows = load_index()
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        digest = hashlib.sha256("".join(r["sha256"] for r in rows).encode()).hexdigest()
        json.dump({"frozen_at_utc": stamp, "reports": len(rows), "collection_sha256": digest},
                  open(os.path.join(DIR, "FROZEN.json"), "w"), indent=1)
        print(f"Collection frozen: {len(rows)} reports; fingerprint {digest[:16]}...")
        return
    if os.path.exists(os.path.join(DIR, "FROZEN.json")):
        print("The collection is frozen (corpus/FROZEN.json). Delete that file to add reports.")
        return
    os.makedirs(os.path.join(DIR, "archive"), exist_ok=True)
    os.makedirs(os.path.join(DIR, "text"), exist_ok=True)
    if not HAVE_PYPDF:
        print("WARNING: the PDF reader is not installed, so PDF text cannot be read.\n"
              "         Install it with:  pip install pypdf   then run this script again.\n")
    rows = load_index()
    if HAVE_PYPDF:
        n = refresh_pdf_text(rows)
        if n:
            save_index(rows)
            print(f"Text read again for {n} saved PDF(s)")
    known = {r["url"] for r in rows}
    added = skipped = 0
    queue = candidates()
    while queue:
        url, source, note = queue.pop(0)
        if url in known:
            continue
        known.add(url)
        try:
            item = fetch(url, source)
            raw = item.pdf_bytes if item.kind == "pdf" else http_get(url).content
        except Exception as e:
            print(f"  could not download {url} ({type(e).__name__})")
            continue
        text = item.text
        if item.kind == "html" and source in FOLLOW:          # e.g. the full report on WHO IRIS
            for a in BeautifulSoup(raw, "html.parser").find_all("a", href=True):
                if re.search(FOLLOW[source], a["href"]) and a["href"] not in known:
                    queue.append((a["href"], source, f"full document linked from {url}"))
        countries = countries_in(text, source)
        pub, from_meta = published_date(raw if item.kind == "html" else b"", text)
        # only a date from the page's metadata may exclude a report as too early;
        # a date found in the text may be an earlier event, not the publication date
        too_early = from_meta and pub and pub < START_DATE
        relevant = ((any(w in text.lower() for w in TOPIC) and countries and not too_early)
                    or (item.kind == "pdf" and not text.strip()))
        if not relevant:
            skipped += 1
            continue
        rid = f"R{len(rows) + 1:04d}"
        ext = "pdf" if item.kind == "pdf" else "html"
        open(os.path.join(DIR, "archive", f"{rid}.{ext}"), "wb").write(raw)
        open(os.path.join(DIR, "text", f"{rid}.txt"), "w", encoding="utf-8").write(text)
        title = ""
        if item.kind == "html":
            t = BeautifulSoup(raw, "html.parser").find("title")
            title = t.get_text(strip=True)[:150] if t else ""
        rows.append({"id": rid, "url": url, "source": source, "title": title, "published": pub,
                     "retrieved": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "language": language(text) if text.strip() else "unknown (scanned)",
                     "countries": ";".join(countries), "kind": item.kind,
                     "sha256": hashlib.sha256(raw).hexdigest(), "n_chars": len(text),
                     "manual_note": note})
        added += 1
        save_index(rows)
    print(f"\n{added} report(s) added, {skipped} unrelated item(s) skipped; "
          f"collection now holds {len(rows)} reports")
    for c in COUNTRIES:
        n = sum(c in r["countries"].split(";") for r in rows)
        fr = sum(c in r["countries"].split(";") and r["language"] == "fr" for r in rows)
        print(f"  {c:<8} {n:4d} reports ({fr} in French)")


if __name__ == "__main__":
    main()
