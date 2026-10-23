PY=env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/python
setup:
	python3.13 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt && cd frontend && npm install
ingest:
	$(PY) scripts/ingest.py data/client_export.xlsx
api:
	cd backend && ../.venv/bin/uvicorn app.main:app --port 8000 --reload
ui:
	cd frontend && npm run dev
test:
	cd backend && ../.venv/bin/python -m pytest -q
erp-objects:
	$(PY) scripts/export_erp_objects.py > airgen/erp_objects.json
