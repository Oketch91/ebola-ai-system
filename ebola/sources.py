"""Find and download new official reports.

Three kinds of source (set in data/sources.json):
  "page":   a listing page; items are the links whose address matches link_pattern
  "rss":    an RSS feed; items are the <item><link> entries
  "single": one page that is updated in place; it counts as new when its text changes
  "sequence": numbered reports (e.g. WHO DON 2026-DON622); the next numbers are tried in turn
"""
import os
import warnings
import hashlib
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "USIU-Africa Ebola outbreak analytics (research; contact ochiengf@usiu.ac.ke)"}
DELAY = 2.0                      # seconds between requests, to be polite to the servers


SEQ_STATE = "data/sequence_state.json"


def http_get(url: str, verify: bool = True) -> requests.Response:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")           # certificate warning when verify=False
        r = requests.get(url, headers=HEADERS, timeout=30, verify=verify)
    time.sleep(DELAY)
    r.raise_for_status()
    return r


def _discover_sequence(src: dict):
    """Try report numbers after the last one found, until max_gap numbers in a row are missing."""
    state = json.load(open(SEQ_STATE)) if os.path.exists(SEQ_STATE) else {}
    found = state.get(src["name"], [])
    n = (max(found) + 1) if found else src["start"]
    misses = tries = 0
    while misses < src.get("max_gap", 3) and tries < 15:     # at most 15 requests per pass
        tries += 1
        try:
            http_get(src["url_template"].format(n=n), src.get("verify_ssl", True))
            found.append(n)
            misses = 0
        except requests.HTTPError:
            misses += 1
        n += 1
    state[src["name"]] = sorted(set(found))
    json.dump(state, open(SEQ_STATE, "w"))
    return [src["url_template"].format(n=k) for k in sorted(set(found))]


def load_sources(path="data/sources.json"):
    return [s for s in json.load(open(path, encoding="utf-8")) if s.get("enabled", True)]


def discover(src: dict, max_items: int = 15):
    """Addresses of the items a source currently lists, oldest first."""
    if src["type"] == "single":
        return [src["url"]]
    if src["type"] == "sequence":
        return _discover_sequence(src)
    r = http_get(src["url"], src.get("verify_ssl", True))
    if src["type"] == "rss":
        links = [i.findtext("link") for i in ET.fromstring(r.content).iter("item")]
    else:
        soup = BeautifulSoup(r.text, "html.parser")
        pat = re.compile(src["link_pattern"])
        links = [urljoin(src["url"], a["href"]) for a in soup.find_all("a", href=True)
                 if pat.search(a["href"])]
    seen, out = set(), []
    for u in links:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return list(reversed(out[:max_items]))          # listing pages put the newest first


@dataclass
class Item:
    url: str
    source: str
    kind: str                     # "html" or "pdf"
    text: str                     # extracted text ("" for a scanned PDF)
    pdf_bytes: bytes
    digest: str                   # fingerprint of the content


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    except Exception:             # pypdf missing or scanned PDF: Claude reads the PDF itself
        return ""


def fetch(url: str, source: str, verify: bool = True) -> Item:
    r = http_get(url, verify)
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        return Item(url, source, "pdf", _pdf_text(r.content), r.content,
                    hashlib.sha256(r.content).hexdigest())
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = re.sub(r"\n\s*\n+", "\n\n", main.get_text("\n")).strip()
    return Item(url, source, "html", text, None, hashlib.sha256(text.encode()).hexdigest())


def is_relevant(item: Item, src: dict) -> bool:
    """Cheap keyword filter before any AI call. A scanned PDF has no text, so it
    is passed on and the model decides."""
    if item.kind == "pdf" and not item.text.strip():
        return True
    t = item.text.lower()
    return (all(k.lower() in t for k in src.get("must_contain", []))
            and any(k.lower() in t for k in src.get("any_of", ["ebola", "bundibugyo"])))
