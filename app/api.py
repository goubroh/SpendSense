"""FastAPI backend. Run: uvicorn app.api:app --reload  ->  docs at http://localhost:8000/docs"""
from typing import List

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from . import analysis, categorizer, qa, store
from .budget import suggest_budget
from .config import SAMPLE_DIR
from .detective import explain_change
from .forecast import forecast_next
from .graph import run_pipeline
from .llm_client import ask as ask_llm, get_llm, status
from .rag import ReportStore

app = FastAPI(title="SpendSense API", version="1.0.0", description="AI personal expense analyst")
llm = get_llm()
reports = ReportStore()


class Question(BaseModel):
    question: str


class CategoryCorrections(BaseModel):
    overrides: dict[str, str]


def _df():
    df = store.load_all()
    if df.empty:
        raise HTTPException(404, "No data loaded. POST /upload or /demo-data first.")
    return df


def _month(df, month):
    if month not in analysis.months(df):
        raise HTTPException(404, f"Month {month} not found. Available: {analysis.months(df)}")
    return month


@app.get("/health")
def health():
    return {"status": "ok", "llm": status(), "llm_available": llm is not None}


@app.post("/upload")
async def upload(files: List[UploadFile] = File(...)):
    try:
        return store.ingest([f.file for f in files], llm)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/demo-data")
def demo_data():
    paths = sorted(SAMPLE_DIR.glob("*.csv"))
    if not paths:
        raise HTTPException(404, "Run `python scripts/generate_sample_data.py` first.")
    return store.ingest(paths, llm)


@app.delete("/data")
def reset():
    store.reset()
    return {"status": "cleared"}


@app.get("/months")
def months():
    return analysis.months(_df())


@app.get("/transactions")
def transactions(month: str | None = None):
    df = _df()
    if month:
        df = df[df["month"] == _month(df, month)]
    df = df.assign(date=df["date"].dt.strftime("%Y-%m-%d"))
    return df.to_dict(orient="records")


@app.get("/categories")
def categories():
    return sorted(set(categorizer.RULES) | {"Others", "Income"})


@app.put("/categories")
def update_categories(corrections: CategoryCorrections):
    _df()
    allowed = set(categorizer.RULES) | {"Others", "Income"}
    for merchant, category in corrections.overrides.items():
        if not merchant.strip() or category not in allowed:
            raise HTTPException(422, f"Invalid merchant or category: {merchant!r}, {category!r}")
    for merchant, category in corrections.overrides.items():
        categorizer.set_override(merchant, category)
    updated = store.recategorize()
    return {"updated": len(corrections.overrides), "transactions": len(updated)}


@app.get("/summary/{month}")
def summary(month: str):
    df = _df()
    return analysis.monthly_summary(df, _month(df, month))


@app.get("/anomalies/{month}")
def anomalies(month: str):
    df = _df()
    m = _month(df, month)
    return {"anomalies": analysis.detect_anomalies(df, m), "unnecessary": analysis.unnecessary_spending(df, m)}


@app.get("/detective/{month}")
def detective(month: str):
    df = _df()
    return explain_change(df, _month(df, month))


@app.post("/detective/{month}/narrate")
def narrate_detective(month: str):
    df = _df()
    findings = explain_change(df, _month(df, month))
    if llm is None:
        raise HTTPException(503, "AI narration is unavailable in offline mode.")
    text = ask_llm(
        llm,
        "You are a friendly financial detective. Use only the given facts.",
        f"Explain in 5 sentences, plain language:\n{findings['headline']}\n"
        + "\n".join(r["explanation"] for r in findings["drivers"][:4]),
    )
    if text is None:
        raise HTTPException(502, "The AI provider could not generate a narration.")
    return {"narration": text}


@app.get("/forecast")
def forecast(month: str | None = None):
    df = _df()
    if month:
        df = df[df["month"] <= _month(df, month)]
    return forecast_next(df)


@app.get("/budget")
def budget(savings_target: float = 0.20, month: str | None = None):
    df = _df()
    if month:
        df = df[df["month"] <= _month(df, month)]
    return suggest_budget(df, savings_target)


@app.post("/report/{month}")
def report(month: str):
    df = _df()
    st = run_pipeline(_month(df, month), llm)
    return {"month": month, "trace": st["trace"], "report_markdown": st["report"]}


@app.get("/reports")
def list_reports():
    return reports.months()


@app.get("/reports/search")
def search_reports(q: str = Query(min_length=1), limit: int = Query(default=4, ge=1, le=20)):
    return reports.search(q, limit)


@app.get("/reports/{month}")
def get_report(month: str):
    text = reports.get(month)
    if text is None:
        raise HTTPException(404, f"Report for {month} not found.")
    return {"month": month, "report_markdown": text}


@app.post("/ask")
def ask(q: Question):
    return qa.answer(q.question, _df(), llm, reports)
