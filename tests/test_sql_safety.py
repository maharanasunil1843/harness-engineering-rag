"""Verify SQL safety / allowlist enforcement."""
import pytest

from app.sql.agent import ALLOWED_TABLES, validate_sql


def test_select_from_allowed_table_passes():
    ok, reason = validate_sql("SELECT * FROM harness_components")
    assert ok, reason
    assert reason == ""


def test_select_with_join_in_allowlist_passes():
    sql = (
        "SELECT c.name FROM harness_components c "
        "JOIN failure_modes f ON c.id = f.component_id"
    )
    ok, reason = validate_sql(sql)
    assert ok, reason


def test_drop_table_rejected():
    ok, reason = validate_sql("DROP TABLE harness_components")
    assert not ok
    assert "SELECT" in reason


def test_insert_rejected():
    ok, _ = validate_sql("INSERT INTO harness_components VALUES (1)")
    assert not ok


def test_select_from_chunks_rejected():
    ok, reason = validate_sql("SELECT * FROM chunks")
    assert not ok
    assert "allowlist" in reason.lower()


def test_select_from_documents_rejected():
    ok, reason = validate_sql("SELECT * FROM documents")
    assert not ok
    assert "allowlist" in reason.lower()


def test_information_schema_rejected():
    ok, _ = validate_sql("SELECT * FROM information_schema.tables")
    assert not ok


def test_pg_extension_rejected():
    ok, _ = validate_sql("SELECT * FROM pg_extension")
    assert not ok


def test_union_rejected():
    sql = (
        "SELECT id FROM harness_components "
        "UNION SELECT id FROM documents"
    )
    ok, reason = validate_sql(sql)
    assert not ok
    assert "UNION" in reason


def test_union_all_rejected():
    sql = (
        "SELECT id FROM harness_components "
        "UNION ALL SELECT id FROM harness_components"
    )
    ok, _ = validate_sql(sql)
    assert not ok


def test_double_dash_comment_rejected():
    ok, reason = validate_sql("SELECT * FROM harness_components -- inject")
    assert not ok
    assert "comment" in reason.lower()


def test_block_comment_rejected():
    ok, reason = validate_sql("SELECT /* hi */ * FROM harness_components")
    assert not ok
    assert "comment" in reason.lower()


def test_multi_statement_rejected():
    ok, reason = validate_sql(
        "SELECT * FROM harness_components; SELECT * FROM harness_components"
    )
    assert not ok
    assert "multi" in reason.lower()


def test_cte_rejected():
    ok, reason = validate_sql(
        "WITH x AS (SELECT 1) SELECT * FROM harness_components"
    )
    assert not ok
    assert "CTE" in reason or "WITH" in reason


def test_select_into_rejected():
    ok, _ = validate_sql(
        "SELECT * INTO new_tbl FROM harness_components"
    )
    assert not ok


def test_empty_rejected():
    ok, _ = validate_sql("")
    assert not ok


def test_allowlist_membership():
    assert "harness_components" in ALLOWED_TABLES
    assert "documents" not in ALLOWED_TABLES
    assert "chunks" not in ALLOWED_TABLES


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT name FROM harnesses",
        "SELECT count(*) FROM benchmark_results",
        "SELECT * FROM practitioners",
        "SELECT a.id FROM harness_components a JOIN harnesses b ON a.harness_id = b.id",
    ],
)
def test_legitimate_queries_pass(sql):
    ok, reason = validate_sql(sql)
    assert ok, f"expected pass but got: {reason}"
