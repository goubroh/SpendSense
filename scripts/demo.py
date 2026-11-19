"""Terminal demo (no UI): ingests sample data, runs the LangGraph workflow, asks questions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import qa, store
from app.config import SAMPLE_DIR
from app.graph import run_pipeline
from app.llm_client import get_llm, status

llm = get_llm()
print(status())
print("Ingest:", store.ingest(sorted(SAMPLE_DIR.glob("*.csv")), llm))
for m in ["2026-08", "2026-09", "2026-10"]:
    st = run_pipeline(m, llm)
    print(f"\n[{m}] workflow:", " -> ".join(st["trace"]))
print("\n" + st["report"])
df = store.load_all()
for q in ["Where did I spend the most money?", "Why did my spending increase?", "Any unusual transactions?", "Predict next month", "How can I save more?"]:
    print(f"\nQ: {q}\nA: {qa.answer(q, df, llm)['answer']}")
