"""Markdown monthly report builder (also the document that gets stored for RAG)."""
from .utils import fmt


def rule_based_insights(summary, detective, unnecessary, forecast, budget) -> str:
    pts = []
    pts.append(f"You spent {fmt(summary['spend'])} against income of {fmt(summary['income'])} (savings rate {summary['savings_rate']:.0f}%).")
    if summary["top_category"]:
        pts.append(f"{summary['top_category']} was your biggest category at {fmt(summary['by_category'][summary['top_category']])}.")
    if detective.get("available") and detective["drivers"]:
        pts.append(detective["drivers"][0]["explanation"])
    if unnecessary:
        best = max(unnecessary, key=lambda x: x["monthly_saving"])
        pts.append(f"Biggest leak to fix: {best['title'].lower()}, potential saving about {fmt(best['monthly_saving'])}/month.")
    if forecast.get("available"):
        pts.append(f"Forecast for {forecast['month']}: {fmt(forecast['total'])} (likely range {fmt(forecast['low'])} to {fmt(forecast['high'])}).")
    if budget.get("available") and budget["tips"]:
        pts.append(budget["tips"][0])
    return "\n".join(f"- {p}" for p in pts)


def build_report(month, summary, anomalies, unnecessary, detective, forecast, budget, insights) -> str:
    L = [f"# Monthly Financial Report: {month}", ""]
    L += ["## Summary", f"- Total spend: {fmt(summary['spend'])}", f"- Income: {fmt(summary['income'])}",
          f"- Net savings: {fmt(summary['net_savings'])} ({summary['savings_rate']:.0f}% savings rate)",
          f"- Invested (SIP etc.): {fmt(summary['invested'])}", f"- Average daily spend: {fmt(summary['daily_avg'])}", ""]
    L += ["## Spending by category"] + [f"- {k}: {fmt(v)}" for k, v in summary["by_category"].items()] + [""]
    L += ["## Top merchants"] + [f"- {m['merchant'].title()}: {fmt(m['total'])} over {m['count']} transactions" for m in summary["top_merchants"]] + [""]
    L += ["## Spending Detective", detective["headline"]]
    if detective.get("available"):
        L += [f"- {d['explanation']}" for d in detective["drivers"][:4]] + [f"- {d['explanation']}" for d in detective["decreases"][:2]]
    L += [""]
    L += ["## Unusual transactions"] + ([f"- {a['date']} {a['merchant'].title()} {fmt(a['amount'])} [{a['severity']}]: {'; '.join(a['reasons'])}" for a in anomalies[:8]] or ["- None detected."]) + [""]
    L += ["## Unnecessary spending"] + ([f"- {u['title']}: {u['detail']}" for u in unnecessary] or ["- None detected."]) + [""]
    if forecast.get("available"):
        L += [f"## Forecast for {forecast['month']}", f"- Expected spend {fmt(forecast['total'])} (80% range {fmt(forecast['low'])} to {fmt(forecast['high'])})"]
        L += [f"- {c}: {fmt(v['forecast'])}" for c, v in list(forecast["by_category"].items())[:6]] + [""]
    if budget.get("available"):
        L += ["## Budget suggestion", f"- Savings target {budget['savings_target_pct']:.0f}% of income {fmt(budget['income'])}; projected savings {fmt(budget['projected_savings'])}"]
        L += [f"- {t}" for t in budget["tips"]] + [""]
    L += ["## Key insights", insights, ""]
    return "\n".join(L)
