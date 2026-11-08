"""The Alembic migrations are the only way a real database changes. These tests keep them honest:
the models must match what `platedex migrate` builds, and every revision must upgrade a database
that already holds data."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

import platedex
from platedex import models  # noqa: F401  (registers tables)
from platedex.db import Base

MIGRATIONS = Path(platedex.__file__).parent / "migrations"


def alembic_cfg(db: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def revisions() -> list[str]:
    """Revision ids from oldest to newest."""
    script = ScriptDirectory.from_config(alembic_cfg(Path("unused.db")))
    return [r.revision for r in reversed(list(script.walk_revisions()))]


def test_single_linear_history():
    script = ScriptDirectory.from_config(alembic_cfg(Path("unused.db")))
    assert len(script.get_heads()) == 1, "Two migration heads: rebase the newer migration onto the other one"
    for rev in script.walk_revisions():
        assert not rev.is_merge_point, f"{rev.revision} is a merge; keep the history linear"


def test_models_match_migrations(tmp_path):
    """Fails when a model changed without a migration. Fix: add one under migrations/versions/."""
    db = tmp_path / "drift.db"
    command.upgrade(alembic_cfg(db), "head")
    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"render_as_batch": True}), Base.metadata)
    engine.dispose()
    assert diff == [], "Models and migrations differ:\n" + "\n".join(map(str, diff))


@pytest.mark.parametrize("start", revisions())
def test_upgrade_keeps_existing_data(tmp_path, start):
    """A database at any earlier revision, with users and plates in it, upgrades to head without losing rows."""
    db = tmp_path / "old.db"
    cfg = alembic_cfg(db)
    command.upgrade(cfg, start)
    con = sqlite3.connect(db)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users', 'plates')")]
    if "users" in tables:
        con.execute("INSERT INTO users (username, role, color, session_version, disabled, created_at) "
                    "VALUES ('keep', 'admin', '#123456', 1, 0, '2026-01-01 00:00:00')")
    con.commit()
    before = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    con.close()

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # running migrate at every start must be harmless

    con = sqlite3.connect(db)
    after = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    assert after == before
    if "users" in tables:
        assert con.execute("SELECT username FROM users").fetchall() == [("keep",)]
    con.close()


def test_migrate_command_on_existing_database(tmp_path, monkeypatch):
    """`platedex migrate` (what the container runs at start) leaves a migrated database at head."""
    from platedex import cli
    from platedex.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    cli._migrate()
    cli._migrate()
    con = sqlite3.connect(tmp_path / "platedex.db")
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == revisions()[-1]
    con.close()
