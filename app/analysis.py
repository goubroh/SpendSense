"""Core pandas/NumPy analytics: summaries, anomaly detection, wasteful-spend finder."""
import numpy as np
import pandas as pd

from .config import DISCRETIONARY, NON_SPEND
from .utils import fmt


def debits(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["kind"] == "debit"]


def months(df: pd.DataFrame) -> list[str]:
    return sorted(df["month"].unique().tolist())


def monthly_summary(df: pd.DataFrame, month: str) -> dict:
    m = df[df["month"] == month]
    d, c = debits(m), m[m["kind"] == "credit"]
    spend_df = d[~d["category"].isin(NON_SPEND)]
    spend, income = float(spend_df["amount"].sum()), float(c["amount"].sum())
    invested = float(d.loc[d["category"] == "Investments", "amount"].sum())
    by_cat = spend_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    merch = (spend_df.groupby("merchant")["amount"].agg(total="sum", count="count")
             .sort_values("total", ascending=False).head(5))
    days = max(1, pd.Period(month).days_in_month)
    top_txn = spend_df.nlargest(5, "amount")[["date", "description", "category", "amount"]]
    return {
        "month": month,
        "spend": spend,
        "income": income,
        "invested": invested,
        "net_savings": income - spend,
        "savings_rate": float((income - spend) / income * 100) if income else 0.0,
        "txn_count": int(len(spend_df)),
        "daily_avg": spend / days,
        "by_category": {k: float(v) for k, v in by_cat.items()},
        "top_category": by_cat.index[0] if len(by_cat) else None,
        "top_merchants": [{"merchant": i, "total": float(r.total), "count": int(r["count"])} for i, r in merch.iterrows()],
        "top_transactions": [{"date": str(r.date.date()), "description": r.description, "category": r.category, "amount": float(r.amount)} for r in top_txn.itertuples()],
    }


def monthly_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """months x categories matrix of spend (investments/transfers excluded)."""
    d = debits(df)
    d = d[~d["category"].isin(NON_SPEND)]
    return d.pivot_table(index="month", columns="category", values="amount", aggfunc="sum").fillna(0).sort_index()


def find_duplicates(m: pd.DataFrame) -> pd.DataFrame:
    """Identical narration + amount within 2 days (ignoring tiny/frequent fares)."""
    m = m[(m["amount"] >= 200) & (m["category"] != "Transport")].sort_values("date")
    parts = []
    for _, g in m.groupby(["description", "amount"]):  # identical narration incl. ref no.
        if len(g) > 1 and (g["date"].diff().dt.days.dropna() <= 2).any():
            parts.append(g.iloc[1:])
    return pd.concat(parts) if parts else m.iloc[0:0]


def detect_anomalies(df: pd.DataFrame, month: str) -> list[dict]:
    """Robust (median/MAD) outlier detection per category + new-merchant + duplicate rules."""
    deb = debits(df)
    deb = deb[~deb["category"].isin(NON_SPEND)]
    cur, hist = deb[deb["month"] == month], deb[deb["month"] < month]
    dup_idx = set(find_duplicates(cur).index)
    known = set(hist["merchant"])
    overall_med = hist["amount"].median() if len(hist) else cur["amount"].median()
    out = []
    for idx, r in cur.iterrows():
        ref = hist.loc[hist["category"] == r.category, "amount"]
        if len(ref) < 5:
            ref = cur.loc[cur["category"] == r.category, "amount"]
        reasons, score = [], 0.0
        if len(ref) >= 5:
            med = ref.median()
            mad = max((ref - med).abs().median(), 0.1 * med, 1.0)
            z = 0.6745 * (r.amount - med) / mad
            if z > 3.5 and r.amount > 2.5 * med:
                reasons.append(f"{r.amount / med:.1f}x the typical {r.category} transaction ({fmt(med)})")
                score = max(score, z)
        if len(hist) and r.merchant not in known and r.amount >= max(1000, 2 * overall_med):
            reasons.append("First time this merchant appears, and the amount is large")
            score = max(score, 3.0)
        if idx in dup_idx:
            reasons.append("Possible duplicate charge (same merchant & amount within 2 days)")
            score = max(score, 6.0)
        if reasons:
            score = float(min(score, 10))
            out.append({
                "date": str(r.date.date()), "description": r.description, "merchant": r.merchant,
                "category": r.category, "amount": float(r.amount), "score": round(score, 1),
                "severity": "high" if score >= 6 else "medium", "reasons": reasons,
            })
    return sorted(out, key=lambda x: -x["score"])


def unnecessary_spending(df: pd.DataFrame, month: str) -> list[dict]:
    """Rule-based leak finder. Each item has a rough monthly saving estimate."""
    m = debits(df[df["month"] == month])
    m = m[~m["category"].isin(NON_SPEND)]
    total = m["amount"].sum()
    items = []
    if total == 0:
        return items

    disc = m[m["category"].isin(DISCRETIONARY)]["amount"].sum()
    if disc / total > 0.35:
        items.append({"type": "discretionary", "title": "High discretionary share",
                      "detail": f"{disc / total:.0%} of spend ({fmt(disc)}) went to wants: food delivery, shopping, travel, entertainment, subscriptions.",
                      "monthly_saving": round(disc * 0.15)})

    fd = m[m["category"] == "Food Delivery"]
    if len(fd) >= 8:
        items.append({"type": "habit", "title": "Frequent food delivery",
                      "detail": f"{len(fd)} orders totalling {fmt(fd['amount'].sum())}. Cooking or ordering half as often would help.",
                      "monthly_saving": round(fd["amount"].sum() * 0.3)})

    subs = m[m["category"] == "Subscriptions"]
    if len(subs):
        s = subs.groupby("merchant")["amount"].sum().sort_values(ascending=False)
        items.append({"type": "subscriptions", "title": f"{len(s)} active subscriptions",
                      "detail": f"{fmt(subs['amount'].sum())}/month: " + ", ".join(f"{k.title()} ({fmt(v)})" for k, v in s.items()) + ". Cancel what you did not use this month.",
                      "monthly_saving": round(subs["amount"].sum() * 0.25)})

    dups = find_duplicates(m)
    if len(dups):
        items.append({"type": "duplicate", "title": "Possible duplicate charges",
                      "detail": "; ".join(f"{r.merchant.title()} {fmt(r.amount)} on {r.date.date()}" for r in dups.itertuples()) + ". Dispute with your bank if not intended.",
                      "monthly_saving": round(dups["amount"].sum())})

    cash = m[m["category"] == "Cash Withdrawal"]["amount"].sum()
    if cash / total > 0.05:
        items.append({"type": "untracked", "title": "Untracked cash",
                      "detail": f"{fmt(cash)} withdrawn as cash ({cash / total:.0%}) cannot be categorised. Prefer UPI for visibility.",
                      "monthly_saving": 0})

    fees = m[m["category"] == "Fees & Charges"]["amount"].sum()
    if fees > 0:
        items.append({"type": "fees", "title": "Bank fees & penalties", "detail": f"{fmt(fees)} paid in charges. Usually avoidable.", "monthly_saving": round(fees)})
    return items
