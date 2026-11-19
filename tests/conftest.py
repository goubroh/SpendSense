import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def df(tmp_path, monkeypatch):
    """Isolated data dir per test, loaded with the demo statements."""
    import importlib

    monkeypatch.setenv("SPENDSENSE_DATA", str(tmp_path))
    import app.config as config
    importlib.reload(config)
    import app.categorizer, app.store, app.rag
    for m in (app.categorizer, app.store, app.rag):
        importlib.reload(m)
    sample = Path(__file__).resolve().parents[1] / "data" / "sample"
    if not list(sample.glob("*.csv")):
        from scripts import generate_sample_data  # noqa
        generate_sample_data.main()
    app.store.ingest(sorted(sample.glob("*.csv")))
    return app.store.load_all()
