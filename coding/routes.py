from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from .db import get_db

bp = Blueprint("web", __name__)

VTT_DIR = Path("vtt")
MP4_DIR = Path("mp4")


# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------

def _parse_vtt(path: Path) -> list[dict]:
    content = path.read_text()
    entries = []
    for match in re.finditer(
        r"(\d{2}:\d{2}:\d{2})\.(\d+) --> .+\n(.+): (.+)", content
    ):
        hh, mm, ss = match.group(1).split(":")
        start_seconds = int(hh) * 3600 + int(mm) * 60 + int(ss)
        entries.append({
            "start_ts": match.group(1),
            "start_seconds": start_seconds,
            "speaker": match.group(3),
            "text": match.group(4),
        })
    return entries


def _find_facilitators(all_entries: dict[str, list[dict]]) -> set[str]:
    file_count: Counter[str] = Counter()
    for entries in all_entries.values():
        for s in {e["speaker"] for e in entries}:
            file_count[s] += 1
    return {name for name, count in file_count.items() if count > 1}


def _load_all_participants() -> tuple[list[str], set[str]]:
    vtt_files = sorted(VTT_DIR.glob("*.vtt"))
    all_entries = {f.stem: _parse_vtt(f) for f in vtt_files}
    facilitators = _find_facilitators(all_entries)
    return sorted(all_entries.keys()), facilitators


def _seconds_to_ts(s: int) -> str:
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _merge_rows(utterances: list[dict], sections: list[dict], notes: list[dict]) -> list[dict]:
    """Merge utterances and sections into a single time-ordered list of rows.

    Each row has a 'type' key of 'utterance', 'section', 'note_instant',
    'note_start', or 'note_end', plus a 'section_id' key on utterances.

    Range notes with content between start/end emit two rows ('note_start' and
    'note_end'). If nothing falls between them they emit a single 'note_instant'
    row instead.
    """
    # Expand range notes into synthetic events
    events: list[dict] = []
    for n in notes:
        if n.get("end_seconds") is not None:
            events.append({"_event": "note_start", "_note": n, "_t": n["start_seconds"]})
            events.append({"_event": "note_end",   "_note": n, "_t": n["end_seconds"]})
        else:
            events.append({"_event": "note_instant", "_note": n, "_t": n["start_seconds"]})

    # Merge all three streams by time
    all_items: list[tuple[int, int, dict]] = []  # (seconds, kind_order, item)
    # kind_order: sections=0, note events=1, utterances=2 (sections/notes before utterances at same time)
    for s in sections:
        all_items.append((s["start_seconds"], 0, {"type": "section", **s}))
    for e in events:
        all_items.append((e["_t"], 1, e))
    for u in utterances:
        all_items.append((u["start_seconds"], 2, {"type": "utterance", **u}))

    all_items.sort(key=lambda x: (x[0], x[1]))

    rows = []
    current_section_id = None

    # Track which range notes have emitted a start_row to decide instant vs split
    note_start_row_idx: dict[int, int] = {}  # note_id -> index of note_start row in rows[]

    for _, _, item in all_items:
        if item.get("type") == "section":
            current_section_id = item["id"]
            rows.append(item)
        elif item.get("_event") == "note_start":
            n = item["_note"]
            idx = len(rows)
            note_start_row_idx[n["id"]] = idx
            rows.append({"type": "note_start", **n})
        elif item.get("_event") == "note_instant":
            n = item["_note"]
            rows.append({"type": "note_instant", **n})
        elif item.get("_event") == "note_end":
            n = item["_note"]
            start_idx = note_start_row_idx.get(n["id"])
            # Check if any utterance/section rows landed between start and now
            between = any(
                rows[i].get("type") in ("utterance", "section")
                for i in range(start_idx + 1, len(rows))
            ) if start_idx is not None else True
            if between:
                rows.append({"type": "note_end", **n})
            else:
                # Collapse into a single instant row
                if start_idx is not None:
                    rows[start_idx] = {"type": "note_instant", **n}
                else:
                    rows.append({"type": "note_instant", **n})
        else:
            # utterance
            item["section_id"] = current_section_id
            rows.append(item)

    return rows


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.get("/")
def index():
    participants, _ = _load_all_participants()
    return render_template("index.html", participants=participants)


@bp.get("/session/<pid>")
def session(pid: str):
    vtt_path = VTT_DIR / f"{pid}.vtt"
    mp4_path = MP4_DIR / f"{pid}.mp4"
    if not vtt_path.exists() or not mp4_path.exists():
        abort(404)

    all_vtt = sorted(VTT_DIR.glob("*.vtt"))
    all_entries = {f.stem: _parse_vtt(f) for f in all_vtt}
    facilitators = _find_facilitators(all_entries)

    utterances = [
        {
            "start_ts": e["start_ts"],
            "start_seconds": e["start_seconds"],
            "speaker": "Facilitator" if e["speaker"] in facilitators else pid,
            "text": e["text"],
        }
        for e in all_entries[pid]
    ]

    db = get_db()
    sections = list(db["sections"].rows_where("pid = ?", [pid], order_by="start_seconds"))
    for s in sections:
        s["start_ts"] = _seconds_to_ts(s["start_seconds"])

    notes = list(db["notes"].rows_where("pid = ?", [pid], order_by="start_seconds"))
    for n in notes:
        n["start_ts"] = _seconds_to_ts(n["start_seconds"])
        if n.get("end_seconds") is not None:
            n["end_ts"] = _seconds_to_ts(n["end_seconds"])

    rows = _merge_rows(utterances, sections, notes)

    return render_template("session.html", pid=pid, rows=rows, sections=sections, notes=notes)


@bp.get("/video/<pid>")
def video(pid: str):
    mp4_path = (MP4_DIR / f"{pid}.mp4").resolve()
    if not mp4_path.exists():
        abort(404)
    return send_file(mp4_path, mimetype="video/mp4", conditional=True)


# ---------------------------------------------------------------------------
# Sections API
# ---------------------------------------------------------------------------

@bp.get("/api/sections/names")
def section_names():
    db = get_db()
    rows = db.execute("SELECT DISTINCT name FROM sections ORDER BY name").fetchall()
    return jsonify([r[0] for r in rows])


@bp.post("/api/sessions/<pid>/sections")
def add_section(pid: str):
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    start_seconds = payload.get("start_seconds")
    if not name or start_seconds is None:
        return jsonify({"error": "name and start_seconds required"}), 400

    db = get_db()
    row_id = db["sections"].insert({
        "pid": pid,
        "name": name,
        "start_seconds": int(start_seconds),
    }).last_pk

    sec = {
        "id": row_id,
        "pid": pid,
        "name": name,
        "start_seconds": int(start_seconds),
        "start_ts": _seconds_to_ts(int(start_seconds)),
    }

    return jsonify(sec)


@bp.delete("/api/sections/<int:section_id>")
def delete_section(section_id: int):
    db = get_db()
    db["sections"].delete(section_id)
    return "", 200


# ---------------------------------------------------------------------------
# Notes API
# ---------------------------------------------------------------------------

@bp.post("/api/sessions/<pid>/notes")
def add_note(pid: str):
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "").strip()
    start_seconds = payload.get("start_seconds")
    end_seconds = payload.get("end_seconds")  # optional
    if not text or start_seconds is None:
        return jsonify({"error": "text and start_seconds required"}), 400

    row = {"pid": pid, "text": text, "start_seconds": int(start_seconds)}
    if end_seconds is not None:
        row["end_seconds"] = int(end_seconds)

    db = get_db()
    row_id = db["notes"].insert(row).last_pk
    note = {**row, "id": row_id, "start_ts": _seconds_to_ts(int(start_seconds))}
    if end_seconds is not None:
        note["end_ts"] = _seconds_to_ts(int(end_seconds))
    return jsonify(note)


@bp.patch("/api/notes/<int:note_id>")
def update_note(note_id: int):
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    db = get_db()
    db["notes"].update(note_id, {"text": text})
    return jsonify({"text": text})


@bp.delete("/api/notes/<int:note_id>")
def delete_note(note_id: int):
    db = get_db()
    db["notes"].delete(note_id)
    return "", 200


# ---------------------------------------------------------------------------
# Codebook page
# ---------------------------------------------------------------------------

@bp.get("/codebook")
def codebook():
    db = get_db()

    codes = list(db.execute("SELECT id, name FROM codes ORDER BY name").fetchall())
    code_list = [{"id": r[0], "name": r[1]} for r in codes]

    # Notes that have at least one code assignment
    coded_note_ids = set(
        r[0] for r in db.execute("SELECT DISTINCT note_id FROM note_codes").fetchall()
    )

    # All notes
    all_notes = list(db.execute(
        "SELECT id, pid, text, start_seconds, end_seconds FROM notes ORDER BY start_seconds"
    ).fetchall())
    all_notes = [{"id": r[0], "pid": r[1], "text": r[2], "start_seconds": r[3], "end_seconds": r[4]} for r in all_notes]

    uncategorized = [n for n in all_notes if n["id"] not in coded_note_ids]

    # For each code, fetch its notes ordered by sort_order
    for c in code_list:
        c["notes"] = list(db.execute(
            "SELECT n.id, n.pid, n.text, n.start_seconds, n.end_seconds "
            "FROM notes n JOIN note_codes nc ON nc.note_id = n.id "
            "WHERE nc.code_id = ? ORDER BY nc.sort_order, nc.id",
            [c["id"]],
        ).fetchall())
        c["notes"] = [{"id": r[0], "pid": r[1], "text": r[2], "start_seconds": r[3], "end_seconds": r[4]} for r in c["notes"]]

    return render_template("codebook.html", codes=code_list, uncategorized=uncategorized)


# ---------------------------------------------------------------------------
# Codes API
# ---------------------------------------------------------------------------

@bp.post("/api/codes")
def create_code():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    row_id = db["codes"].insert({"name": name}).last_pk
    return jsonify({"id": row_id, "name": name}), 201


@bp.patch("/api/codes/<int:code_id>")
def update_code(code_id: int):
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    db["codes"].update(code_id, {"name": name})
    return jsonify({"id": code_id, "name": name})


@bp.delete("/api/codes/<int:code_id>")
def delete_code(code_id: int):
    db = get_db()
    db.execute("DELETE FROM note_codes WHERE code_id = ?", [code_id])
    db["codes"].delete(code_id)
    return "", 200


@bp.post("/api/codes/<int:code_id>/notes/<int:note_id>")
def assign_note_to_code(code_id: int, note_id: int):
    db = get_db()
    exists = db.execute(
        "SELECT 1 FROM note_codes WHERE code_id = ? AND note_id = ?",
        [code_id, note_id],
    ).fetchone()
    if not exists:
        max_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM note_codes WHERE code_id = ?",
            [code_id],
        ).fetchone()[0]
        db["note_codes"].insert({
            "note_id": note_id, "code_id": code_id,
            "source": "note", "sort_order": max_order + 1,
        })
    return "", 204


@bp.delete("/api/codes/<int:code_id>/notes/<int:note_id>")
def remove_note_from_code(code_id: int, note_id: int):
    db = get_db()
    db.execute(
        "DELETE FROM note_codes WHERE code_id = ? AND note_id = ?",
        [code_id, note_id],
    )
    return "", 204


@bp.put("/api/codes/<int:code_id>/order")
def reorder_code_notes(code_id: int):
    """Accepts {note_ids: [id, id, …]} and updates sort_order to match."""
    payload = request.get_json(silent=True) or {}
    note_ids = payload.get("note_ids", [])
    if not isinstance(note_ids, list):
        return jsonify({"error": "note_ids must be a list"}), 400
    db = get_db()
    for i, note_id in enumerate(note_ids):
        db.execute(
            "UPDATE note_codes SET sort_order = ? WHERE code_id = ? AND note_id = ?",
            [i, code_id, note_id],
        )
    return "", 204
