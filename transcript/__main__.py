"""Convert VTT transcripts to simplified markdown format."""

import re
from collections import Counter
from pathlib import Path

VTT_DIR = Path("vtt")
MD_DIR = Path("md")


def parse_vtt(path: Path) -> list[dict]:
    """Parse a VTT file into a list of {start, speaker, text} entries."""
    content = path.read_text()
    entries = []
    for match in re.finditer(
        r"(\d{2}:\d{2}:\d{2})\.\d+ --> .+\n(.+): (.+)", content
    ):
        entries.append({
            "start": match.group(1),
            "speaker": match.group(2),
            "text": match.group(3),
        })
    return entries


def find_facilitators(all_entries: dict[str, list[dict]]) -> set[str]:
    """Facilitators appear in more than one file (participants appear in only one)."""
    file_count: Counter[str] = Counter()
    for entries in all_entries.values():
        speakers = set(e["speaker"] for e in entries)
        for s in speakers:
            file_count[s] += 1
    return {name for name, count in file_count.items() if count > 1}


def format_transcript(entries: list[dict], participant_id: str, facilitators: set[str]) -> str:
    """Format entries as one line per utterance."""
    lines = []
    for entry in entries:
        speaker = entry["speaker"]
        label = "Facilitator" if speaker in facilitators else participant_id
        lines.append(f"{entry['start']} - {label}: {entry['text']}")
    return "\n".join(lines) + "\n"


def main():
    MD_DIR.mkdir(exist_ok=True)
    vtt_files = sorted(VTT_DIR.glob("*.vtt"))

    all_entries = {}
    for vtt_file in vtt_files:
        all_entries[vtt_file.stem] = parse_vtt(vtt_file)

    facilitators = find_facilitators(all_entries)
    print(f"Detected facilitator(s): {facilitators}")

    for pid, entries in all_entries.items():
        output = format_transcript(entries, pid, facilitators)
        out_path = MD_DIR / f"{pid}.md"
        out_path.write_text(output)
        print(f"Wrote {out_path} ({len(entries)} utterances)")


if __name__ == "__main__":
    main()
