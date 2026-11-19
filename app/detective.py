"""The AI Spending Detective: explains WHY this month differs from your recent baseline.
Pure-pandas root-cause analysis; the LLM only narrates the structured findings."""
import pandas as pd

from .analysis import debits
from .config import NON_SPEND
from .utils import fmt, pct


def explain_change(df: pd.DataFrame, month: str, lookback: int = 3) -> dict:
    deb = debits(df)
    deb = deb[~deb["category"].isin(NON_SPEND)]
    prior = [m for m in sorted(deb["month"].unique()) if m < month][-lookback:]
    if not prior:
        return {"available": False, "headline": "Upload at least two months of statements so the Detective has a baseline."}

    cur, base = deb[deb["month"] == month], deb[deb["month"].isin(prior)]
    cur_total = float(cur["amount"].sum())
    base_total = float(base.groupby("month")["amount"].sum().mean())
    change = cur_total - base_total
    threshold = max(300.0, 0.03 * base_total)

    rows = []
    for cat in sorted(set(cur["category"]) | set(base["category"])):
        c, b = cur[cur["category"] == cat], base[base["category"] == cat]
        base_amt = float(b["amount"].sum() / len(prior))
        delta = float(c["amount"].sum()) - base_amt
        if abs(delta) < threshold:
            continue
        n_c, n_b = len(c), len(b) / len(prior)
        a_c = float(c["amount"].mean()) if n_c else 0.0
        a_b = float(b["amount"].mean()) if len(b) else 0.0
        count_effect = (n_c - n_b) * a_b if len(b) else delta
        ticket_effect = delta - count_effect
        new_merchants = sorted(set(c["merchant"]) - set(b["merchant"]))
        big = c.nlargest(3, "amount")
        driver = "frequency" if abs(count_effect) >= abs(ticket_effect) else "ticket size"
        if not len(b):
            driver = "new category"
        rows.append({
            "category": cat, "baseline": base_amt, "current": float(c["amount"].sum()), "delta": delta,
            "delta_pct": pct(float(c["amount"].sum()), base_amt) if base_amt else None,
            "txns_baseline": round(n_b, 1), "txns_current": n_c,
            "avg_ticket_baseline": a_b, "avg_ticket_current": a_c,
            "count_effect": float(count_effect), "ticket_effect": float(ticket_effect), "driver": driver,
            "new_merchants": new_merchants[:5],
            "top_transactions": [{"date": str(r.date.date()), "description": r.description, "amount": float(r.amount)} for r in big.itertuples()],
        })

    rises = sorted([r for r in rows if r["delta"] > 0], key=lambda r: -r["delta"])
    falls = sorted([r for r in rows if r["delta"] < 0], key=lambda r: r["delta"])
    total_rise = sum(r["delta"] for r in rises) or 1.0
    for r in rises:
        r["share_of_increase"] = r["delta"] / total_rise
        r["explanation"] = _explain(r)
    for r in falls:
        r["explanation"] = f"{r['category']} fell by {fmt(-r['delta'])} ({fmt(r['baseline'])} → {fmt(r['current'])})."

    direction = "up" if change >= 0 else "down"
    top = rises[:3]
    headline = (f"{month}: you spent {fmt(cur_total)}, {direction} {abs(pct(cur_total, base_total)):.0f}% "
                f"({fmt(abs(change))}) versus your {len(prior)}-month average of {fmt(base_total)}.")
    if top and change > 0:
        share = sum(r["delta"] for r in top) / total_rise
        headline += " " + ", ".join(r["category"] for r in top) + f" account for {share:.0%} of the increase."
    return {"available": True, "month": month, "baseline_months": prior, "current_total": cur_total,
            "baseline_total": base_total, "change": change, "change_pct": pct(cur_total, base_total),
            "headline": headline, "drivers": rises, "decreases": falls[:3]}


def _explain(r: dict) -> str:
    pctxt = f" (+{r['delta_pct']:.0f}%)" if r["delta_pct"] is not None else ""
    s = f"{r['category']} rose by {fmt(r['delta'])}{pctxt}: {fmt(r['baseline'])} → {fmt(r['current'])}. "
    if r["driver"] == "ticket size":
        s += f"Average ticket went from {fmt(r['avg_ticket_baseline'])} to {fmt(r['avg_ticket_current'])}"
        if r["top_transactions"]:
            t = r["top_transactions"][0]
            s += f"; largest item {fmt(t['amount'])} on {t['date']} ({t['description'][:40]})"
        s += "."
    elif r["driver"] == "frequency":
        s += f"You made {r['txns_current']} transactions vs ~{r['txns_baseline']:.0f} usually."
    else:
        s += "This category was not part of your recent baseline."
    if r["new_merchants"]:
        s += " New merchants: " + ", ".join(m.title() for m in r["new_merchants"]) + "."
    return s
