"""Conversational Q&A: grounded in computed facts (no hallucinated numbers) + RAG over past reports.
With an LLM -> natural answers. Without -> deterministic rule-based answers."""
import json
import re

import pandas as pd

from . import analysis
from .budget import suggest_budget
from .detective import explain_change
from .forecast import forecast_next
from .llm_client import ask
from .rag import ReportStore
from .utils import fmt

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_month(q: str, df: pd.DataFrame) -> str:
    """Find a month in the question ('2026-09', 'September', 'sep'); default = latest month."""
    ms = analysis.months(df)
    if m := re.search(r"\d{4}-\d{2}", q):
        return m.group(0) if m.group(0) in ms else ms[-1]
    for word in re.findall(r"[a-z]+", q.lower()):
        if len(word) >= 3 and word[:3] in _MONTHS and (word == "may" or len(word) >= 4 or word[:3] != "mar"):
            cand = [x for x in ms if int(x[5:]) == _MONTHS[word[:3]]]
            if cand:
                return cand[-1]
    return ms[-1]


def build_facts(df: pd.DataFrame, month: str) -> dict:
    mat = analysis.monthly_matrix(df)
    prior = df[df["month"] <= month]
    return {
        "month": month,
        "summary": analysis.monthly_summary(df, month),
        "category_by_month": {m: {c: round(v) for c, v in row.items() if v} for m, row in mat.iterrows()},
        "anomalies": analysis.detect_anomalies(df, month)[:6],
        "leaks": analysis.unnecessary_spending(df, month),
        "detective": explain_change(df, month),
        "forecast": forecast_next(prior),
        "budget": suggest_budget(prior),
    }


def _rule_answer(q: str, f: dict) -> str:
    ql, s = q.lower(), f["summary"]
    if re.search(r"predict|forecast|next month|expect", ql) and f["forecast"].get("available"):
        fc = f["forecast"]
        top = ", ".join(f"{c} {fmt(v['forecast'])}" for c, v in list(fc["by_category"].items())[:3])
        return f"I expect about {fmt(fc['total'])} in {fc['month']} (likely {fmt(fc['low'])} to {fmt(fc['high'])}). Biggest: {top}."
    if re.search(r"budget|save|saving|cut", ql) and f["budget"].get("available"):
        b = f["budget"]
        return f"To save {b['savings_target_pct']:.0f}% of income ({fmt(b['income'])}): " + " ".join(b["tips"][:3])
    if re.search(r"unusual|anomal|strange|suspicious|odd|duplicate", ql):
        if not f["anomalies"]:
            return f"No unusual transactions in {s['month']}."
        return f"Unusual in {s['month']}: " + " | ".join(f"{a['date']} {a['merchant'].title()} {fmt(a['amount'])} ({a['reasons'][0]})" for a in f["anomalies"][:4])
    if re.search(r"why|increase|higher|compare|more than|jump|rise|went up", ql):
        d = f["detective"]
        return d["headline"] + ("" if not d.get("available") else " " + " ".join(x["explanation"] for x in d["drivers"][:2]))
    if re.search(r"most|biggest|highest|top|where", ql):
        m = s["top_merchants"][0] if s["top_merchants"] else None
        txt = f"In {s['month']} your top category was {s['top_category']} ({fmt(s['by_category'].get(s['top_category'], 0))})"
        return txt + (f", and your top merchant was {m['merchant'].title()} ({fmt(m['total'])})." if m else ".")
    return (f"In {s['month']} you spent {fmt(s['spend'])} on {s['txn_count']} transactions (income {fmt(s['income'])}, "
            f"savings rate {s['savings_rate']:.0f}%). Top category: {s['top_category']}.")


def answer(question: str, df: pd.DataFrame, llm=None, reports: ReportStore | None = None) -> dict:
    reports = reports or ReportStore()
    month = parse_month(question, df)
    facts = build_facts(df, month)
    hits = reports.search(question, k=3)
    rule = _rule_answer(question, facts)
    text = None
    if llm is not None:
        ctx = "\n\n".join(f"[Report {h['month']} / {h['section']}]\n{h['text'][:600]}" for h in hits)
        text = ask(llm,
                   "You are SpendSense, a personal finance assistant. Answer ONLY from FACTS and REPORTS. Quote exact figures, never invent data, "
                   "say so if the data cannot answer. Be concise (max ~6 sentences) and end with one practical suggestion when relevant.",
                   f"FACTS (JSON):\n{json.dumps(facts, default=str)[:12000]}\n\nREPORTS:\n{ctx}\n\nQUESTION: {question}")
    return {"answer": text or rule, "mode": "llm" if text else "rule-based", "month": month,
            "sources": [{"month": h["month"], "section": h["section"]} for h in hits]}
