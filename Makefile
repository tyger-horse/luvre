test:
	python -m pytest tests/ -q

run:
	uvicorn app.main:app --reload
