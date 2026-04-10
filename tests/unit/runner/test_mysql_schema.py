from sqlalchemy.dialects import mysql
from sqlalchemy import String, UniqueConstraint
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


def test_control_store_indexed_varchars_fit_mysql_utf8mb4_limits():
    from swe.app.runner.repo.mysql_schema import CONTROL_STORE_METADATA

    indexed_columns = set()
    composite_limits = []
    for table in CONTROL_STORE_METADATA.sorted_tables:
        indexed_columns.update(table.primary_key.columns)
        composite_limits.append((table.primary_key, list(table.primary_key.columns)))
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                indexed_columns.update(constraint.columns)
                composite_limits.append((constraint, list(constraint.columns)))

    oversized = [
        f"{column.table.name}.{column.name}={column.type.length}"
        for column in indexed_columns
        if isinstance(column.type, String)
        and column.type.length is not None
        and column.type.length > 191
    ]

    assert oversized == []

    oversized_composites = []
    for constraint, columns in composite_limits:
        total_chars = sum(
            column.type.length
            for column in columns
            if isinstance(column.type, String)
            and column.type.length is not None
        )
        if total_chars > 768:
            oversized_composites.append(
                f"{columns[0].table.name}.{constraint.name or 'primary'}="
                f"{total_chars}"
            )

    assert oversized_composites == []
