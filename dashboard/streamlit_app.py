"""SpendSense dashboard. Run: streamlit run dashboard/streamlit_app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.config import CURRENCY
from app.utils import fmt
from dashboard.api_client import APIError, request as api_request

st.set_page_config(page_title="SpendSense · AI Expense Analyst", page_icon="💸", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.6rem;max-width:1250px}
[data-testid="stMetric"]{background:rgba(120,120,160,.08);border:1px solid rgba(120,120,160,.18);padding:14px 16px;border-radius:14px}
.card{border-left:4px solid #6C63FF;background:rgba(108,99,255,.07);padding:12px 16px;border-radius:10px;margin:8px 0}
.card.bad{border-color:#E5484D;background:rgba(229,72,77,.07)} .card.good{border-color:#30A46C;background:rgba(48,164,108,.07)}
h1,h2,h3{letter-spacing:-.01em}
</style>""", unsafe_allow_html=True)


def api_call(method: str, path: str, **kwargs):
    try:
        return api_request(method, path, **kwargs)
    except APIError as exc:
        st.error(str(exc))
        st.stop()


def display_transactions(rows):
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------- sidebar ----------------
st.sidebar.title("💸 SpendSense")
st.sidebar.caption("AI personal expense analyst")
files = st.sidebar.file_uploader("Upload bank statement CSVs", type="csv", accept_multiple_files=True)
if st.sidebar.button("Ingest uploaded files", disabled=not files, width="stretch"):
    upload_files = [("files", (f.name, f.getvalue(), "text/csv")) for f in files]
    result = api_call("POST", "/upload", files=upload_files)
    st.sidebar.success(f"Added {result['added']} transactions")
    st.rerun()
c1, c2 = st.sidebar.columns(2)
if c1.button("Load demo data", width="stretch"):
    result = api_call("POST", "/demo-data")
    st.sidebar.success(f"Loaded {result['total']} transactions")
    st.rerun()
if c2.button("Clear data", width="stretch"):
    api_call("DELETE", "/data")
    st.rerun()
health = api_call("GET", "/health")
st.sidebar.caption(health["llm"])

try:
    months = api_request("GET", "/months")
except APIError as exc:
    if exc.status_code != 404 or exc.detail != "No data loaded. POST /upload or /demo-data first.":
        st.error(str(exc))
        st.stop()
    st.title("SpendSense")
    st.info("Upload one or more monthly bank CSVs (or click **Load demo data**) to begin. "
            "Columns needed: Date, Description/Narration, and Debit/Credit or Amount.")
    st.stop()

df = display_transactions(api_call("GET", "/transactions"))
summaries = {m: api_call("GET", f"/summary/{m}") for m in months}
month = st.sidebar.selectbox("Month", months, index=len(months) - 1)
S = summaries[month]
prev = months[months.index(month) - 1] if months.index(month) > 0 else None
P = summaries[prev] if prev else None

st.title(f"Financial overview · {month}")
k = st.columns(4)
k[0].metric("Spent", fmt(S["spend"]), f"{fmt(S['spend'] - P['spend'])} vs {prev}" if P else None, delta_color="inverse")
k[1].metric("Income", fmt(S["income"]))
k[2].metric("Savings rate", f"{S['savings_rate']:.0f}%", f"{S['savings_rate'] - P['savings_rate']:+.0f} pts" if P else None)
k[3].metric("Invested (SIP)", fmt(S["invested"]))

tabs = st.tabs(["📊 Overview", "🕵️ Spending Detective", "⚠️ Unusual & Waste", "🔮 Forecast & Budget", "💬 Ask AI", "🗂️ Reports (RAG)", "🧾 Transactions"])

# ---------------- overview ----------------
with tabs[0]:
    a, b = st.columns([1, 1.3])
    cat = pd.Series(S["by_category"]).reset_index()
    cat.columns = ["category", "amount"]
    a.plotly_chart(px.pie(cat, names="category", values="amount", hole=.55, title="Where the money went"), width="stretch")
    matrix = pd.DataFrame([{"month": m, **summaries[m]["by_category"]} for m in months]).fillna(0).set_index("month")
    mat = matrix.reset_index().melt("month", var_name="category", value_name="amount")
    b.plotly_chart(px.bar(mat, x="month", y="amount", color="category", title="Monthly spend by category"), width="stretch")
    st.subheader("Top merchants")
    st.dataframe(pd.DataFrame(S["top_merchants"]).assign(total=lambda x: x["total"].round(0)), hide_index=True, width="stretch")

# ---------------- detective ----------------
with tabs[1]:
    findings = api_call("GET", f"/detective/{month}")
    st.subheader("Why did my spending change?")
    st.markdown(f'<div class="card {"bad" if findings.get("available") and findings["change"] > 0 else "good"}">{findings["headline"]}</div>', unsafe_allow_html=True)
    if findings.get("available"):
        rows = findings["drivers"] + findings["decreases"]
        chart = pd.DataFrame({"category": [r["category"] for r in rows], "change": [r["delta"] for r in rows]}).sort_values("change")
        fig = go.Figure(go.Bar(x=chart["change"], y=chart["category"], orientation="h", marker_color=["#E5484D" if v > 0 else "#30A46C" for v in chart["change"]]))
        fig.update_layout(title=f"Change vs {len(findings['baseline_months'])}-month average ({CURRENCY})", height=360)
        st.plotly_chart(fig, width="stretch")
        for r in findings["drivers"]:
            with st.expander(f"▲ {r['category']}  +{fmt(r['delta'])}  ·  {r['share_of_increase']:.0%} of the increase  ·  driver: {r['driver']}", expanded=r is findings["drivers"][0]):
                st.write(r["explanation"])
                m = st.columns(3)
                m[0].metric("Transactions", r["txns_current"], f"{r['txns_current'] - r['txns_baseline']:+.0f} vs usual")
                m[1].metric("Avg ticket", fmt(r["avg_ticket_current"]), fmt(r["avg_ticket_current"] - r["avg_ticket_baseline"]))
                m[2].metric("Frequency vs ticket effect", f"{fmt(r['count_effect'])} / {fmt(r['ticket_effect'])}")
                st.table(pd.DataFrame(r["top_transactions"]))
        for r in findings["decreases"]:
            st.markdown(f'<div class="card good">▼ {r["explanation"]}</div>', unsafe_allow_html=True)
        if health["llm_available"] and st.button("Narrate with AI"):
            narration = api_call("POST", f"/detective/{month}/narrate")
            st.write(narration["narration"])

# ---------------- anomalies ----------------
with tabs[2]:
    analysis = api_call("GET", f"/anomalies/{month}")
    st.subheader("Unusual transactions")
    if analysis["anomalies"]:
        st.dataframe(pd.DataFrame([{**{k: item[k] for k in ("date", "merchant", "category", "amount", "severity", "score")}, "why": "; ".join(item["reasons"])} for item in analysis["anomalies"]]), hide_index=True, width="stretch")
    else:
        st.success("Nothing unusual this month.")
    st.subheader("Potentially unnecessary spending")
    for item in analysis["unnecessary"]:
        st.markdown(f'<div class="card bad"><b>{item["title"]}</b> · est. saving {fmt(item["monthly_saving"])}/mo<br>{item["detail"]}</div>', unsafe_allow_html=True)
    if analysis["unnecessary"]:
        st.metric("Total estimated monthly saving", fmt(sum(item["monthly_saving"] for item in analysis["unnecessary"])))

# ---------------- forecast & budget ----------------
with tabs[3]:
    forecast = api_call("GET", "/forecast", params={"month": month})
    st.subheader(f"Forecast for {forecast['month']}: {fmt(forecast['total'])}")
    st.caption(f"80% range {fmt(forecast['low'])} – {fmt(forecast['high'])} · method: {forecast['method']}" + (f" · backtest error ≈ {forecast['backtest_mape']:.0f}%" if forecast["backtest_mape"] else ""))
    history = pd.DataFrame({"month": list(forecast["history"]) + [forecast["month"]], "spend": list(forecast["history"].values()) + [forecast["total"]], "kind": ["actual"] * len(forecast["history"]) + ["forecast"]})
    st.plotly_chart(px.bar(history, x="month", y="spend", color="kind", color_discrete_map={"actual": "#6C63FF", "forecast": "#F5A623"}), width="stretch")
    st.subheader("Personalised budget")
    target = st.slider("Savings target (% of income)", 5, 40, 20) / 100
    budget = api_call("GET", "/budget", params={"savings_target": target, "month": month})
    m = st.columns(3)
    m[0].metric("Avg income", fmt(budget["income"]))
    m[1].metric("Suggested total spend", fmt(budget["total_cap"]), fmt(budget["total_cap"] - budget["avg_spend"]), delta_color="inverse")
    m[2].metric("Projected savings", fmt(budget["projected_savings"]))
    st.dataframe(pd.DataFrame(budget["rows"]).round(0), hide_index=True, width="stretch")
    for tip in budget["tips"]:
        st.markdown(f"- {tip}")

# ---------------- ask ----------------
with tabs[4]:
    st.subheader("Ask about your money")
    examples = ["Where did I spend the most money?", "Why did my spending increase this month?", "Any unusual transactions?", "Predict my spending next month", "How can I save more?"]
    cols = st.columns(len(examples))
    picked = next((example for col, example in zip(cols, examples) if col.button(example, width="stretch")), None)
    st.session_state.setdefault("chat", [])
    for role, text in st.session_state["chat"]:
        st.chat_message(role).write(text)
    question = st.chat_input("e.g. How much did I spend on food in September?") or picked
    if question:
        st.chat_message("user").write(question)
        result = api_call("POST", "/ask", json={"question": question})
        sources = "" if not result["sources"] else "\n\n_Retrieved: " + ", ".join(f"{source['month']} · {source['section']}" for source in result["sources"]) + "_"
        answer = result["answer"] + sources
        st.chat_message("assistant").write(answer)
        st.session_state["chat"] += [("user", question), ("assistant", answer)]

# ---------------- reports / RAG ----------------
with tabs[5]:
    st.subheader("Monthly reports")
    if st.button(f"Generate report for {month} (LangGraph workflow)", type="primary"):
        with st.spinner("Running multi-step analysis…"):
            result = api_call("POST", f"/report/{month}")
        st.success("Workflow: " + " → ".join(result["trace"]))
    left, right = st.columns([1, 1.4])
    saved = api_call("GET", "/reports")
    with left:
        query = st.text_input("Search past reports (RAG)", placeholder="when did I last overspend on shopping?")
        if query:
            matches = api_call("GET", "/reports/search", params={"q": query, "limit": 4})
            for match in matches:
                st.markdown(f"**{match['month']} · {match['section']}** (score {match['score']:.2f})")
                st.caption(match["text"][:300])
    with right:
        if saved:
            selected_report = st.selectbox("Open report", saved, index=len(saved) - 1)
            report = api_call("GET", f"/reports/{selected_report}")["report_markdown"]
            st.markdown(report)
            st.download_button("Download .md", report, f"report_{selected_report}.md")
        else:
            st.info("No reports yet. Generate one on the left.")

# ---------------- transactions ----------------
with tabs[6]:
    current = df[df["month"] == month]
    categories = api_call("GET", "/categories")
    st.caption("Wrong category? Fix it below: the correction is remembered for that merchant.")
    edited = st.data_editor(current[["date", "description", "merchant", "amount", "kind", "category"]], hide_index=True, width="stretch",
                            column_config={"category": st.column_config.SelectboxColumn(options=categories)}, disabled=["date", "description", "merchant", "amount", "kind"], key=f"ed{month}")
    if st.button("Save category corrections"):
        changed = edited[edited["category"] != current["category"].values]
        overrides = {row.merchant: row.category for row in changed.itertuples()}
        if overrides:
            result = api_call("PUT", "/categories", json={"overrides": overrides})
            st.success(f"Updated {result['updated']} merchant rules")
            st.rerun()
        else:
            st.info("No category changes to save.")
