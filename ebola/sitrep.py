"""AI situation report: Claude writes a short summary from the model outputs,
and every number in the summary is checked against those outputs."""
import json
import re

from .extraction import DEFAULT_MODEL, call_anthropic

SYSTEM = """You write short situation reports on an Ebola disease outbreak for public health
decision-makers in Kenya. Use ONLY the numbers and dates in the JSON you are given; never add
a number of your own, and never round differently from the JSON except to fewer decimals.
Write in plain English, 150-200 words, in four short paragraphs:
1. Situation: cases, deaths, settings of exposure, date of the last onset.
2. Transmission: the control reproduction number with its 95% credible interval, and what it means.
3. Outlook: the probability that transmission has ended, and the dates it reaches 0.95 and 0.99,
   compared with the WHO 42-day rule.
4. Actions: two or three practical recommendations that follow from these numbers.
If a value is missing, say it is not yet available. State that estimates come from a
mathematical model and carry uncertainty. No headings, no bullet points."""


def _numbers(text: str):
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def check_numbers(report: str, data: dict):
    """Numbers in the report that cannot be traced to the model outputs."""
    allowed = set()
    for v in _numbers(json.dumps(data)):
        allowed.add(v)
        try:
            x = float(v)
            for d in range(0, 4):
                allowed.add(f"{round(x, d):.{d}f}")
            for d in range(0, 2):                               # proportions as percentages
                allowed.add(f"{round(100 * x, d):.{d}f}")
        except ValueError:
            pass
    allowed |= {"42", "95", "0.95", "0.99", "99", "1", "2", "3", "21"}   # rule, thresholds, counts of items
    return sorted(n for n in _numbers(report) if n not in allowed and n.lstrip("0") not in allowed)


def write_sitrep(data: dict, model: str = DEFAULT_MODEL, llm=call_anthropic):
    data = {k: v for k, v in data.items() if not k.startswith("curve")}
    text = llm(SYSTEM, "Model outputs (JSON):\n" + json.dumps(data, indent=1), model, None).strip()
    return text, check_numbers(text, data)
