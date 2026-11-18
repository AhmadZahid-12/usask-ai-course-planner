"""Explicit upgrades for the local SQLite student workspace."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import click
from flask import Flask
from sqlalchemy import Column, Integer, MetaData, Table, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from app.db import db

LATEST_VERSION = 2
_VERSION_TABLE = Table(
    "student_schema_versions",
    MetaData(),
    Column("version", Integer, primary_key=True),
)


def _database_path() -> Path | None:
    name = db.engine.url.database
    return Path(name) if name and name != ":memory:" else None


def student_storage_ready(*models) -> bool:
    """Check for the requested tables without making a missing SQLite file."""
    path = _database_path()
    if path is not None and not path.is_file():
        return False
    inspector = inspect(db.engine)
    return all(inspector.has_table(model if isinstance(model, str) else model.__tablename__) for model in models)


def _models_for_version(version: int) -> tuple:
    if version == 1:
        from app.calendar_store import CalendarEvent
        from app.models import CourseCache, Plan

        return Plan, CourseCache, CalendarEvent

    from app.course_workspace import CourseMaterial, StudentCourse

    return StudentCourse, CourseMaterial


def _back_up(database: Path, destination: Path) -> None:
    if database.resolve() == destination.resolve():
        raise ValueError("Choose a different path for the backup.")
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        # SQLite's backup API includes committed changes from the write-ahead log.
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(destination)) as output:
                source.backup(output)
    except Exception:
        destination.unlink()
        raise


def upgrade_student_schema(
    *, backup: Path | None = None, target: int = LATEST_VERSION
) -> list[int]:
    """Apply pending additive migrations. Existing files require a new backup path."""
    if db.engine.dialect.name != "sqlite":
        raise ValueError("Student workspace migrations currently support SQLite.")
    if not 1 <= target <= LATEST_VERSION:
        raise ValueError("Choose a supported schema version.")
    database = _database_path()
    database_existed = database is not None and database.is_file()
    if database is not None:
        database.parent.mkdir(parents=True, exist_ok=True)

    with db.engine.connect() as connection:
        # Hold a write reservation so the backup reflects the state being upgraded.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        existing_tables = inspect(connection).get_table_names()
        if _VERSION_TABLE.name in existing_tables:
            applied = set(connection.scalars(select(_VERSION_TABLE.c.version)))
        else:
            applied = set()
        if applied != set(range(1, max(applied, default=0) + 1)) or any(
            version > LATEST_VERSION for version in applied
        ):
            raise ValueError("The database has an unsupported migration history.")

        pending = [version for version in range(1, target + 1) if version not in applied]
        if not pending:
            connection.rollback()
            return []

        if database is not None and (database_existed or existing_tables):
            if backup is None:
                raise ValueError("Supply --backup with a new path before upgrading an existing database.")
            _back_up(database, backup)

        _VERSION_TABLE.create(connection, checkfirst=True)
        for version in pending:
            for model in _models_for_version(version):
                model.__table__.create(connection, checkfirst=True)
            connection.execute(_VERSION_TABLE.insert().values(version=version))
        connection.commit()
        return pending


def register_student_migrations(app: Flask) -> None:
    @app.cli.command("migrate-student")
    @click.option("--backup", type=click.Path(path_type=Path, dir_okay=False))
    def migrate_student(backup: Path | None):
        """Initialize or upgrade student workspace tables."""
        try:
            versions = upgrade_student_schema(backup=backup)
        except (OSError, ValueError, sqlite3.Error, SQLAlchemyError) as error:
            raise click.ClickException(str(error)) from error
        if versions:
            click.echo(f"Student schema upgraded to version {versions[-1]}.")
        else:
            click.echo("Student schema is already up to date.")
