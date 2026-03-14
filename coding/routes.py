from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from flask import Blueprint, abort, render_template, send_file

bp = Blueprint("web", __name__)

VTT_DIR = Path("vtt")
MP4_DIR = Path("mp4")


# ---------------------------------------------------------------------------
# VTT parsing (copied from transcript package — no import dependency)
# ---------------------------------------------------------------------------

def _parse_vtt(path: Path) -> list[dict]:
    """Parse a VTT file into a list of {start_ts, start_seconds, speaker, text} entries."""
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
    """Facilitators appear in more than one transcript file."""
    file_count: Counter[str] = Counter()
    for entries in all_entries.values():
        for s in {e["speaker"] for e in entries}:
            file_count[s] += 1
    return {name for name, count in file_count.items() if count > 1}


def _load_all_participants() -> tuple[list[str], set[str]]:
    """Return sorted participant IDs and the set of facilitator speaker names."""
    vtt_files = sorted(VTT_DIR.glob("*.vtt"))
    all_entries = {f.stem: _parse_vtt(f) for f in vtt_files}
    facilitators = _find_facilitators(all_entries)
    return sorted(all_entries.keys()), facilitators


# ---------------------------------------------------------------------------
# Routes
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

    # Load just this participant's transcript to determine facilitators
    all_vtt = sorted(VTT_DIR.glob("*.vtt"))
    all_entries = {f.stem: _parse_vtt(f) for f in all_vtt}
    facilitators = _find_facilitators(all_entries)

    entries = all_entries[pid]
    # Label speakers for display
    utterances = [
        {
            "start_ts": e["start_ts"],
            "start_seconds": e["start_seconds"],
            "speaker": "Facilitator" if e["speaker"] in facilitators else pid,
            "text": e["text"],
        }
        for e in entries
    ]

    return render_template("session.html", pid=pid, utterances=utterances)


@bp.get("/video/<pid>")
def video(pid: str):
    mp4_path = (MP4_DIR / f"{pid}.mp4").resolve()
    if not mp4_path.exists():
        abort(404)
    return send_file(mp4_path, mimetype="video/mp4", conditional=True)
