"""Tiny persistence layer: one deduplicated transactions.csv. Swap for SQLite/Postgres in production."""
import pandas as pd

from .categorizer import categorize
from .config import TXN_FILE
from .loader import load_csv

_KEY = ["date", "description", "amount", "kind"]


def load_all() -> pd.DataFrame:
    if not TXN_FILE.exists():
        return pd.DataFrame(columns=_KEY + ["month", "merchant", "category"])
    df = pd.read_csv(TXN_FILE, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def ingest(files, llm=None) -> dict:
    """files: paths or file-like objects. Returns ingest stats."""
    frames = [load_csv(f) for f in files]
    if not frames:
        raise ValueError("No files provided")
    new = categorize(pd.concat(frames, ignore_index=True), llm)
    old = load_all()
    # dedupe re-uploaded statements, but keep genuine same-day twins: number repeats inside each source first
    for frame in (old, new):
        frame["_n"] = frame.groupby(_KEY).cumcount()
    merged = pd.concat([old, new], ignore_index=True)
    before = len(old)
    merged = merged.drop_duplicates(subset=_KEY + ["_n"]).drop(columns="_n")
    merged.sort_values("date").to_csv(TXN_FILE, index=False)
    return {"added": len(merged) - before, "total": len(merged), "months": sorted(merged["month"].unique().tolist())}


def recategorize(llm=None):
    df = load_all()
    if df.empty:
        return df
    df = categorize(df.drop(columns=["category"], errors="ignore"), llm)
    df.to_csv(TXN_FILE, index=False)
    return df


def reset():
    if TXN_FILE.exists():
        TXN_FILE.unlink()
