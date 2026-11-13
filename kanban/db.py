"""SQLite helpers. One connection per request, closed automatically."""
import sqlite3

from flask import current_app, g

COLUMNS = ["backlog", "todo", "in_progress", "done"]
PRIORITIES = ["low", "medium", "high"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'backlog',
    priority    TEXT    NOT NULL DEFAULT 'medium',
    assignee    TEXT    NOT NULL DEFAULT '',
    points      INTEGER,
    due_date    TEXT,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    get_db().executescript(SCHEMA)


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
