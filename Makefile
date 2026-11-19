setup:  ; pip install -r requirements.txt && python scripts/generate_sample_data.py
test:   ; pytest -q
api:    ; uvicorn app.api:app --reload
ui:     ; streamlit run dashboard/streamlit_app.py
up:     ; docker compose up --build
