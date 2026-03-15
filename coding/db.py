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

    if "notes" not in db.table_names():
        db["notes"].create({
            "id": int,
            "pid": str,
            "text": str,
            "start_seconds": int,
            "end_seconds": int,  # NULL for instantaneous notes
        }, pk="id", not_null={"pid", "text", "start_seconds"})
        db["notes"].create_index(["pid", "start_seconds"])

    if "codes" not in db.table_names():
        db["codes"].create({
            "id": int,
            "name": str,
        }, pk="id", not_null={"name"})

    if "note_codes" not in db.table_names():
        # Many-to-many: a note can belong to multiple codes.
        # source distinguishes how the association was created:
        #   'note'      — created from a session note
        #   'highlight' — future: created from a transcript utterance highlight
        # sort_order controls display order within a code (lower = earlier).
        db["note_codes"].create({
            "id": int,
            "note_id": int,
            "code_id": int,
            "source": str,  # 'note' | 'highlight' | …
            "sort_order": int,  # display order within the code
        }, pk="id", not_null={"note_id", "code_id", "source", "sort_order"},
           foreign_keys=[
               ("note_id", "notes", "id"),
               ("code_id", "codes", "id"),
           ])
        db["note_codes"].create_index(["note_id"])
        db["note_codes"].create_index(["code_id"])
    elif "sort_order" not in db["note_codes"].columns_dict:
        db.execute("ALTER TABLE note_codes ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
