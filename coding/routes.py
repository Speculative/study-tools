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


def _merge_rows(utterances: list[dict], sections: list[dict]) -> list[dict]:
    """Merge utterances and sections into a single time-ordered list of rows.

    Each row has a 'type' key of 'utterance' or 'section', plus a 'section_id'
    key on utterances indicating which section they belong to (None if before any section).
    """
    rows = []
    ui, si = 0, 0
    current_section_id = None

    while ui < len(utterances) or si < len(sections):
        take_section = (
            si < len(sections) and (
                ui >= len(utterances) or
                sections[si]["start_seconds"] <= utterances[ui]["start_seconds"]
            )
        )
        if take_section:
            sec = sections[si]
            current_section_id = sec["id"]
            rows.append({"type": "section", **sec})
            si += 1
        else:
            utt = utterances[ui]
            rows.append({"type": "utterance", "section_id": current_section_id, **utt})
            ui += 1

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

    rows = _merge_rows(utterances, sections)

    return render_template("session.html", pid=pid, rows=rows, sections=sections)


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

    # If htmx request, return an HTML fragment
    if request.headers.get("HX-Request"):
        return render_template("_section_row.html", sec=sec)

    return jsonify(sec)


@bp.delete("/api/sections/<int:section_id>")
def delete_section(section_id: int):
    db = get_db()
    db["sections"].delete(section_id)
    return "", 200
