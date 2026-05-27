"""Text-to-SQL agent with schema grounding, prompt caching, and self-correction."""
import os
import time

import psycopg
from anthropic import Anthropic
from pydantic import BaseModel

from app.config import get_settings
from app.observability.tracing import traced, track_token_usage

_CATALOG_TABLES = [
    "harness_components",
    "failure_modes",
    "practitioners",
    "harnesses",
    "benchmark_results",
    "component_addresses_failure",
]

# Cached DDL string — populated once per process, never re-fetched
_schema_ddl: str | None = None

_MAX_RETRIES = 3


class SQLResult(BaseModel):
    sql: str
    rows: list[dict]
    explanation: str
    retries: int
    execution_time_ms: float


def _build_schema_ddl() -> str:
    global _schema_ddl
    if _schema_ddl is not None:
        return _schema_ddl

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        parts: list[str] = []
        for table in _CATALOG_TABLES:
            cols = conn.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            ).fetchall()
            col_defs = ", ".join(
                f"{c[0]} {c[1]}{'?' if c[2] == 'YES' else ''}" for c in cols
            )
            parts.append(f"  {table}({col_defs})")

        # Also fetch FK relationships
        fks = conn.execute(
            """
            SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = ANY(%s)
            """,
            (_CATALOG_TABLES,),
        ).fetchall()
        fk_lines = [f"  {r[0]}.{r[1]} → {r[2]}" for r in fks]

    _schema_ddl = "Tables:\n" + "\n".join(parts)
    if fk_lines:
        _schema_ddl += "\n\nForeign keys:\n" + "\n".join(fk_lines)
    return _schema_ddl


def _safe_sql(sql: str) -> str:
    """Raise ValueError for any non-SELECT or multi-statement SQL."""
    stripped = sql.strip().lstrip("```sql").lstrip("```").strip()
    # Drop trailing code fence if present
    if stripped.endswith("```"):
        stripped = stripped[:-3].strip()
    first_word = stripped.split()[0].upper() if stripped.split() else ""
    if first_word != "SELECT":
        raise ValueError(f"Only SELECT queries are allowed, got: {first_word}")
    if ";" in stripped:
        raise ValueError("Multi-statement SQL is not allowed (semicolons rejected)")
    return stripped


def _rows_to_dicts(rows, cursor) -> list[dict]:
    cols = [d.name for d in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


@traced("text_to_sql")
async def text_to_sql(question: str) -> SQLResult:
    s = get_settings()
    schema_ddl = _build_schema_ddl()
    client = Anthropic(api_key=s.anthropic_api_key)

    system_block = [
        {
            "type": "text",
            "text": (
                "You are a Postgres SQL expert. Generate a single SELECT query that answers "
                "the user's question using only the tables and columns listed below. "
                "Return ONLY the raw SQL — no markdown, no explanation, no code fences.\n\n"
                f"{schema_ddl}"
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]

    messages = [{"role": "user", "content": question}]
    sql = ""
    rows: list[dict] = []
    retries = 0
    exec_ms = 0.0
    last_error = ""

    for attempt in range(_MAX_RETRIES + 1):
        # Generate SQL
        resp = client.messages.create(
            model=s.worker_model,
            max_tokens=512,
            system=system_block,
            messages=messages,
        )
        raw_sql = resp.content[0].text.strip()
        track_token_usage(
            s.worker_model,
            resp.usage.input_tokens,
            resp.usage.output_tokens,
            cost=0.0,
        )

        try:
            sql = _safe_sql(raw_sql)
        except ValueError as e:
            last_error = str(e)
            messages.append({"role": "assistant", "content": raw_sql})
            messages.append({"role": "user", "content": f"Error: {last_error}. Generate a valid SELECT query."})
            retries += 1
            continue

        # Execute SQL
        try:
            t0 = time.perf_counter()
            with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = _rows_to_dicts(cur.fetchall(), cur)
            exec_ms = (time.perf_counter() - t0) * 1000
            break
        except Exception as e:
            last_error = str(e)
            messages.append({"role": "assistant", "content": raw_sql})
            messages.append({
                "role": "user",
                "content": f"SQL execution error: {last_error}. Fix the query and try again.",
            })
            retries += 1
            if attempt == _MAX_RETRIES:
                return SQLResult(
                    sql=sql,
                    rows=[],
                    explanation=f"Failed after {retries} retries. Last error: {last_error}",
                    retries=retries,
                    execution_time_ms=exec_ms,
                )

    # Generate natural-language explanation
    rows_preview = rows[:10]
    explain_resp = client.messages.create(
        model=s.worker_model,
        max_tokens=512,
        system=system_block,
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "content": sql},
            {
                "role": "user",
                "content": (
                    f"The query returned {len(rows)} rows. First 10: {rows_preview}\n\n"
                    "Write a concise natural-language answer to the original question based on these results."
                ),
            },
        ],
    )
    explanation = explain_resp.content[0].text.strip()
    track_token_usage(
        s.worker_model,
        explain_resp.usage.input_tokens,
        explain_resp.usage.output_tokens,
        cost=0.0,
    )

    return SQLResult(
        sql=sql,
        rows=rows,
        explanation=explanation,
        retries=retries,
        execution_time_ms=exec_ms,
    )
