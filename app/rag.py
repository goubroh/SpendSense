"""RAG over previous monthly reports. Reports are chunked by section and retrieved with TF-IDF
cosine similarity (no external services). To upgrade: swap `search` for Chroma/FAISS + embeddings."""
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config


class ReportStore:
    def __init__(self, directory=None):
        self.dir = directory or config.REPORT_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, month: str, text: str):
        (self.dir / f"{month}.md").write_text(text, encoding="utf-8")

    def months(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("*.md"))

    def get(self, month: str) -> str | None:
        p = self.dir / f"{month}.md"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def _chunks(self) -> list[dict]:
        out = []
        for m in self.months():
            for sec in re.split(r"\n(?=## )", self.get(m)):
                title = sec.strip().splitlines()[0].lstrip("# ").strip() if sec.strip() else ""
                if len(sec.strip()) > 40:
                    out.append({"month": m, "section": title, "text": sec.strip()})
        return out

    def search(self, query: str, k: int = 3, exclude_month: str | None = None) -> list[dict]:
        chunks = [c for c in self._chunks() if c["month"] != exclude_month]
        if not chunks:
            return []
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        mat = vec.fit_transform([f"{c['month']} {c['section']} {c['text']}" for c in chunks] + [query])
        sims = cosine_similarity(mat[-1], mat[:-1]).ravel()
        order = sims.argsort()[::-1][:k]
        return [{**chunks[i], "score": float(sims[i])} for i in order if sims[i] > 0]
