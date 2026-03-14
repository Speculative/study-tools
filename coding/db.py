from __future__ import annotations

from pathlib import Path

import sqlite_utils
from flask import g

DB_PATH = Path("coding.db")


def get_db() -> sqlite_utils.Database:
    if "db" not in g:
        g.db = sqlite_utils.Database(DB_PATH)
        _init_schema(g.db)
    return g.db


def _init_schema(db: sqlite_utils.Database) -> None:
    if "sections" not in db.table_names():
        db["sections"].create({
            "id": int,
            "pid": str,
            "name": str,
            "start_seconds": int,
        }, pk="id", not_null={"pid", "name", "start_seconds"})
        db["sections"].create_index(["pid", "start_seconds"])
