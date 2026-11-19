"""Personalised budget: keeps a savings target, protects essentials, trims wants proportionally."""
import pandas as pd

from .analysis import debits, monthly_matrix
from .config import DISCRETIONARY, ESSENTIAL
from .utils import fmt


def suggest_budget(df: pd.DataFrame, savings_target: float = 0.20, lookback: int = 3) -> dict:
    mat = monthly_matrix(df).tail(lookback)
    if mat.empty:
        return {"available": False}
    credits = df[(df["kind"] == "credit") & (df["month"].isin(mat.index))]
    income = float(credits.groupby("month")["amount"].sum().mean()) if len(credits) else 0.0
    avg = mat.mean()
    essential = float(avg[[c for c in avg.index if c in ESSENTIAL]].sum())
    flexible = float(avg.sum() - essential)
    target_savings = income * savings_target
    room = income - target_savings - essential          # what is left for "wants" + others
    factor = 1.0 if flexible <= room or flexible == 0 else max(0.5, room / flexible)

    rows = []
    for cat, a in avg.sort_values(ascending=False).items():
        if cat in ESSENTIAL:
            cap, why = a * 1.05, "Essential: 5% buffer for price changes"
        else:
            cap = a * factor
            why = ("Trimmed to hit your savings goal" if factor < 1 else "Within limits") + (" (discretionary)" if cat in DISCRETIONARY else "")
        rows.append({"category": cat, "avg_spend": float(a), "suggested_cap": float(cap), "change": float(cap - a), "rationale": why})
    total_cap = sum(r["suggested_cap"] for r in rows)
    return {
        "available": True, "income": income, "savings_target_pct": savings_target * 100,
        "projected_savings": income - total_cap, "avg_spend": float(avg.sum()), "total_cap": total_cap,
        "feasible": factor >= 0.5 and income - total_cap >= 0, "rows": rows,
        "tips": _tips(rows, income, total_cap, savings_target),
    }


def _tips(rows, income, total_cap, target):
    tips = []
    biggest = [r for r in rows if r["change"] < -100][:3]
    for r in biggest:
        tips.append(f"Cap {r['category']} at {fmt(r['suggested_cap'])} (saves {fmt(-r['change'])}/month).")
    if income and (income - total_cap) / income < target:
        tips.append("Even after trimming wants, the savings goal is tight: consider raising income or lowering the target to 15%.")
    tips.append("Automate savings/SIP on salary day so the money moves before you can spend it.")
    return tips
