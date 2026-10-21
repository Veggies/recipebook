"""SQLite storage. Each recipe is one JSON document; a few columns are pulled out for listing."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_db_path: Path | None = None


def init(path: Path) -> None:
    global _db_path
    _db_path = path
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                source_url TEXT,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recipes_source ON recipes(source_url)")


@contextmanager
def _connect():
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_recipe(row) -> dict:
    return {
        **json.loads(row["data"]),
        "id": row["id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _split(recipe: dict) -> tuple[dict, str]:
    data = {k: v for k, v in recipe.items() if k not in ("id", "status", "created_at", "updated_at")}
    return data, recipe.get("status") or "ready"


def list_recipes(query: str = "", status: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM recipes WHERE 1=1", []
    for word in query.split():
        sql += " AND (title LIKE ? OR data LIKE ?)"
        args += [f"%{word}%"] * 2
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY title COLLATE NOCASE"
    with _connect() as conn:
        return [_row_to_recipe(r) for r in conn.execute(sql, args)]


def get(recipe_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return _row_to_recipe(row) if row else None


def find_by_source(url: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE source_url = ?", (url,)).fetchone()
    return _row_to_recipe(row) if row else None


def create(recipe: dict) -> dict:
    data, status = _split(recipe)
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO recipes (title, status, source_url, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (data["title"], status, data.get("source_url") or None, json.dumps(data), now, now),
        )
        new_id = cur.lastrowid
    return get(new_id)


def update(recipe_id: int, recipe: dict) -> dict | None:
    data, status = _split(recipe)
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE recipes SET title = ?, status = ?, source_url = ?, data = ?, updated_at = ? WHERE id = ?",
            (data["title"], status, data.get("source_url") or None, json.dumps(data), _now(), recipe_id),
        )
    return get(recipe_id) if cur.rowcount else None


def delete(recipe_id: int) -> bool:
    with _connect() as conn:
        return conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,)).rowcount > 0
