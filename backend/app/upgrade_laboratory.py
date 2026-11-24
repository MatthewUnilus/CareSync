"""Offline upgrade from the CareSync schema immediately before the lab workflow."""

from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import AddConstraint, CreateColumn, CreateTable, DropConstraint

from app.config import get_settings
from app.db import build_engine
from app.models import AuditEntry, Investigation, User


def _upgrade(connection: Connection) -> None:
    inspector = inspect(connection)
    sqlite = connection.dialect.name == "sqlite"
    for model, name, new_value in (
        (User, "ck_users_role", "'laboratory'"),
        (AuditEntry, "ck_audit_log_action", "'publish_lab_result'"),
    ):
        table = model.__table__
        if not inspector.has_table(table.name):
            continue
        checks = {check["name"]: check["sqltext"] for check in inspector.get_check_constraints(table.name)}
        if new_value in checks.get(name, ""):
            continue
        if name not in checks:
            raise RuntimeError(f"Expected {name} on {table.name}")
        constraint = next(
            item for item in table.constraints
            if isinstance(item, CheckConstraint) and item.name == name
        )
        if not sqlite:
            connection.execute(DropConstraint(constraint))
            connection.execute(AddConstraint(constraint))
            continue

        if {column["name"] for column in inspector.get_columns(table.name)} != set(table.c.keys()):
            raise RuntimeError(f"Unexpected schema for {table.name}")
        indexes = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
            (table.name,),
        ).scalars().all()
        temporary = f"lab_upgrade_{table.name}"
        ddl = str(CreateTable(table).compile(dialect=connection.dialect))
        connection.exec_driver_sql(ddl.replace(f"CREATE TABLE {table.name} ", f"CREATE TABLE {temporary} ", 1))
        columns = ", ".join(table.c.keys())
        connection.exec_driver_sql(
            f"INSERT INTO {temporary} ({columns}) SELECT {columns} FROM {table.name}"
        )
        connection.exec_driver_sql(f"DROP TABLE {table.name}")
        connection.exec_driver_sql(f"ALTER TABLE {temporary} RENAME TO {table.name}")
        for index in indexes:
            connection.exec_driver_sql(index)

    table = Investigation.__table__
    if not inspector.has_table(table.name):
        return
    existing = {column["name"] for column in inspector.get_columns(table.name)}
    for name in (
        "lab_origin_ward", "lab_sent_at", "lab_sent_by_user_id", "lab_received_at",
        "lab_received_by_user_id", "result_published_by_user_id",
    ):
        column = table.c[name]
        if name in existing:
            continue
        definition = str(CreateColumn(column).compile(dialect=connection.dialect))
        if column.foreign_keys:
            definition += " REFERENCES users(id)"
        connection.exec_driver_sql(f"ALTER TABLE {table.name} ADD COLUMN {definition}")


def upgrade(engine: Engine) -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            _upgrade(connection)
        return
    if engine.dialect.name != "sqlite":
        raise ValueError(f"Unsupported database: {engine.dialect.name}")

    # SQLite cannot replace a CHECK in place. Disable FK enforcement for the
    # rebuild on this connection, then check every reference before committing.
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.commit()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            _upgrade(connection)
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                raise RuntimeError("Laboratory upgrade would leave invalid foreign keys")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()


if __name__ == "__main__":
    engine = build_engine(get_settings().database_url)
    try:
        upgrade(engine)
    finally:
        engine.dispose()
    print("Laboratory schema is ready.")
