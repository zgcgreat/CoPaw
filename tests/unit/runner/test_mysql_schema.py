from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable


def test_control_store_schema_compiles_for_mysql():
    from swe.app.runner.repo.mysql_schema import CONTROL_STORE_METADATA

    ddl_statements = [
        str(CreateTable(table).compile(dialect=mysql.dialect()))
        for table in CONTROL_STORE_METADATA.sorted_tables
    ]

    assert any("CREATE TABLE chat_runs" in ddl for ddl in ddl_statements)
    assert any(
        "CREATE TABLE session_checkpoints" in ddl
        for ddl in ddl_statements
    )
