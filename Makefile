.PHONY: ingest ingest-chunks-only verify test-agent smoke lint eval eval-quick

ingest:
	uv run python -m ingestion.run --dir data/raw

ingest-chunks-only:
	uv run python -m ingestion.run --dir data/raw --skip-entities

verify:
	@uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); \
	import psycopg; conn = psycopg.connect(os.environ['DATABASE_URL']); \
	cur = conn.cursor(); \
	[print(f'{t}: {cur.execute(f\"SELECT COUNT(*) FROM {t}\").fetchone()[0]}') \
	 for t in ['documents','chunks','harness_components','failure_modes','practitioners','harnesses','benchmark_results']]"

test-agent:
	uv run python scripts/test_agent.py

smoke:
	uv run python scripts/smoke_test.py

lint:
	uv run ruff check .

eval:
	uv run python -m evals.run_eval

eval-quick:
	uv run python -m evals.run_eval --quick
