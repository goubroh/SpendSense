"""LangGraph workflow: load -> summary -> anomalies/leaks -> (detective if history) -> forecast -> budget -> report.
The conditional edge after `anomalies` is what makes this a real graph rather than a straight pipeline."""
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from . import analysis, store
from .budget import suggest_budget
from .detective import explain_change
from .forecast import forecast_next
from .llm_client import ask
from .rag import ReportStore
from .report import build_report, rule_based_insights


class State(TypedDict, total=False):
    df: Any
    month: str
    summary: dict
    anomalies: list
    unnecessary: list
    detective: dict
    forecast: dict
    budget: dict
    insights: str
    report: str
    trace: list


def _t(s, name):
    return (s.get("trace") or []) + [name]


def build_graph(llm=None, reports: ReportStore | None = None):
    reports = reports or ReportStore()

    def load(s):
        df = store.load_all()
        if df.empty:
            raise ValueError("No transactions loaded. Upload CSV files first.")
        return {"df": df, "month": s.get("month") or analysis.months(df)[-1], "trace": _t(s, "load")}

    def summary(s):
        return {"summary": analysis.monthly_summary(s["df"], s["month"]), "trace": _t(s, "summary")}

    def anomalies(s):
        return {"anomalies": analysis.detect_anomalies(s["df"], s["month"]),
                "unnecessary": analysis.unnecessary_spending(s["df"], s["month"]), "trace": _t(s, "anomalies")}

    def detective(s):
        return {"detective": explain_change(s["df"], s["month"]), "trace": _t(s, "detective")}

    def no_history(s):
        return {"detective": explain_change(s["df"], s["month"]), "trace": _t(s, "detective(skipped: no history)")}

    def forecast(s):
        d = s["df"][s["df"]["month"] <= s["month"]]  # never peek past the selected month
        return {"forecast": forecast_next(d), "trace": _t(s, "forecast")}

    def budget(s):
        d = s["df"][s["df"]["month"] <= s["month"]]
        return {"budget": suggest_budget(d), "trace": _t(s, "budget")}

    def report(s):
        base = rule_based_insights(s["summary"], s["detective"], s["unnecessary"], s["forecast"], s["budget"])
        insights = base
        if llm is not None:
            past = reports.search("overspending unusual categories budget", k=2, exclude_month=s["month"])
            ctx = "\n\n".join(f"[{p['month']}] {p['text'][:700]}" for p in past)
            facts = f"SUMMARY:{s['summary']}\nDETECTIVE:{s['detective'].get('headline')} {[d['explanation'] for d in s['detective'].get('drivers', [])[:3]]}\nANOMALIES:{s['anomalies'][:5]}\nLEAKS:{s['unnecessary']}\nFORECAST:{s['forecast'].get('total')}\nBUDGET TIPS:{s['budget'].get('tips')}\nPAST REPORTS:\n{ctx}"
            ai = ask(llm, "You are SpendSense, a careful personal finance analyst. Use ONLY the facts given. Never invent numbers.",
                     f"Write 5 concise, specific, personalised insight bullets (and one action for next month) from these facts. Mention trends versus past reports when available.\n\n{facts}")
            insights = ai or base
        text = build_report(s["month"], s["summary"], s["anomalies"], s["unnecessary"], s["detective"], s["forecast"], s["budget"], insights)
        reports.save(s["month"], text)
        return {"insights": insights, "report": text, "trace": _t(s, "report")}

    g = StateGraph(State)
    for name, fn in [("load", load), ("summary", summary), ("anomalies", anomalies), ("detective", detective),
                     ("no_history", no_history), ("forecast", forecast), ("budget", budget), ("report", report)]:
        g.add_node(name, fn)
    g.set_entry_point("load")
    g.add_edge("load", "summary")
    g.add_edge("summary", "anomalies")
    g.add_conditional_edges("anomalies", lambda s: "detective" if any(m < s["month"] for m in analysis.months(s["df"])) else "no_history")
    g.add_edge("detective", "forecast")
    g.add_edge("no_history", "forecast")
    g.add_edge("forecast", "budget")
    g.add_edge("budget", "report")
    g.add_edge("report", END)
    return g.compile()


def run_pipeline(month: str | None = None, llm=None) -> dict:
    return build_graph(llm).invoke({"month": month} if month else {})
