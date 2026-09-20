.PHONY: ui test run clean

ui:
	python -m uvicorn server.app:app --host 0.0.0.0 --port 8000

test:
	$env:PYTHONPATH="src"; python -m unittest discover tests

clean:
	rm -rf runs/temp_* uploads/*
