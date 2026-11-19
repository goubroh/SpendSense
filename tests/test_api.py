from fastapi.testclient import TestClient


def test_api_flow(df):
    import importlib, app.api
    importlib.reload(app.api)
    c = TestClient(app.api.app)
    assert c.get("/health").status_code == 200
    assert c.get("/months").status_code == 200
    assert len(c.get("/transactions", params={"month": "2026-10"}).json()) > 0
    assert "Groceries" in c.get("/categories").json()
    assert c.get("/summary/2026-10").json()["income"] == 45000
    assert c.get("/summary/1999-01").status_code == 404
    assert c.get("/detective/2026-10").json()["available"]
    assert c.get("/forecast").json()["month"] == "2026-11"
    assert c.get("/forecast", params={"month": "2026-09"}).json()["month"] == "2026-10"
    assert c.get("/budget", params={"month": "2026-10", "savings_target": 0.25}).json()["available"]
    report = c.post("/report/2026-10").json()
    assert "report_markdown" in report
    assert c.get("/reports/2026-10").json()["report_markdown"] == report["report_markdown"]
    assert c.get("/reports/search", params={"q": "spending"}).status_code == 200
    assert c.post("/ask", json={"question": "unusual transactions?"}).json()["answer"]
    assert c.put("/categories", json={"overrides": {"Zynthos Labs": "Groceries"}}).json()["updated"] == 1
    assert c.put("/categories", json={"overrides": {"Zynthos Labs": "Invalid"}}).status_code == 422
