import io

import pandas as pd

from app import analysis, loader
from app.budget import suggest_budget
from app.categorizer import rule_category
from app.detective import explain_change
from app.forecast import forecast_next


def test_loader_handles_signed_amount_format():
    csv = io.StringIO("Txn Date,Details,Amount\n2026-01-05,UPI-SWIGGY-ORDER 123@ybl,-350\n2026-01-06,SALARY,50000\n")
    out = loader.load_csv(csv)
    assert list(out["kind"]) == ["debit", "credit"]
    assert out.loc[0, "merchant"] == "SWIGGY"


def test_categorizer_rules():
    assert rule_category("UPI-SWIGGY-ORDER 99") == "Food Delivery"
    assert rule_category("AMAZON PRIME MEMBERSHIP") == "Subscriptions"  # specific rule beats generic Amazon
    assert rule_category("ECOM-AMAZON PAY-111") == "Shopping"
    assert rule_category("UPI-RANDOM-STORE") == "Others"


def test_ingest_is_idempotent(df):
    import app.store as store
    from pathlib import Path
    n = len(df)
    store.ingest(sorted((Path(__file__).resolve().parents[1] / "data" / "sample").glob("*.csv")))
    assert len(store.load_all()) == n


def test_summary_excludes_investments(df):
    s = analysis.monthly_summary(df, "2026-10")
    assert s["income"] == 45000 and s["invested"] == 3000
    assert "Investments" not in s["by_category"]


def test_anomalies_find_planted_events(df):
    a = analysis.detect_anomalies(df, "2026-10")
    text = " ".join(x["merchant"] + " " + " ".join(x["reasons"]) for x in a)
    assert any(x["amount"] == 18999 for x in a)
    assert "duplicate" in text.lower()
    assert not [x for x in analysis.detect_anomalies(df, "2026-06") if x["amount"] > 10000]


def test_detective_explains_october_spike(df):
    d = explain_change(df, "2026-10")
    assert d["available"] and d["change"] > 0
    cats = [x["category"] for x in d["drivers"]]
    assert "Shopping" in cats and "Food Delivery" in cats
    food = next(x for x in d["drivers"] if x["category"] == "Food Delivery")
    assert abs(food["count_effect"] + food["ticket_effect"] - food["delta"]) < 1e-6


def test_detective_needs_baseline(df):
    assert explain_change(df, "2026-05")["available"] is False


def test_forecast_and_backtest(df):
    f = forecast_next(df)
    assert f["month"] == "2026-11" and f["low"] < f["total"] < f["high"]
    assert f["backtest_mape"] is not None


def test_budget_hits_savings_goal(df):
    b = suggest_budget(df, 0.20)
    assert b["available"] and b["projected_savings"] > 0
    assert sum(r["suggested_cap"] for r in b["rows"]) == b["total_cap"]


def test_langgraph_pipeline_and_rag(df):
    from app.graph import run_pipeline
    from app.rag import ReportStore
    st = run_pipeline("2026-10")
    assert st["trace"][0] == "load" and "report" in st["trace"][-1]
    assert "Spending Detective" in st["report"]
    run_pipeline("2026-09")
    hits = ReportStore().search("duplicate Netflix charge headphones", k=2)
    assert hits and hits[0]["month"] in {"2026-10", "2026-09"}


def test_qa_rule_based(df):
    from app import qa
    r = qa.answer("Where did I spend the most money in September?", df)
    assert r["month"] == "2026-09" and "Rent" in r["answer"] or "top category" in r["answer"]
    r = qa.answer("Why did my spending increase?", df)
    assert "2026-10" in r["answer"]
    assert "2026-11" in qa.answer("predict next month", df)["answer"]
