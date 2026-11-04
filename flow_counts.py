"""Numbers for the flow diagram and the Results (no AI, no cost).

    python flow_counts.py
"""
import os

import pandas as pd

idx = pd.read_csv("corpus/corpus_index.csv")
ev = pd.read_csv("evaluation/evaluable_reports.csv")
has_text = idx["n_chars"].fillna(0).astype(int) > 0
print(f"Reports in the frozen collection: {len(idx)}")
print(f"  in French: {(idx['language'] == 'fr').sum()}; in English: {(idx['language'] == 'en').sum()}; "
      f"no readable text (scanned): {(~has_text).sum()}")
print(f"  with readable text: {has_text.sum()}")
print(f"    not stating a reference pair of figures: {has_text.sum() - len(ev)}")
print(f"    stating a reference pair (evaluated): {len(ev)}")
insp = idx["source"] == "DRC INSP situation reports"
print(f"INSP situation reports collected: {insp.sum()} (no readable text: {(insp & ~has_text).sum()}; "
      f"evaluated: {(ev['source'] == 'DRC INSP situation reports').sum()})")
