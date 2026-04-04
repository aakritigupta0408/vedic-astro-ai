#!/usr/bin/env python3
"""
ingest_vedastro.py — Ingest VedAstro reference birth charts.

Input:  data/raw/vedastro/*.json  (VedAstro export format)
Output: data/raw/vedastro/cases.json (normalised case list)

Expected VedAstro JSON format (per file or per-entry in an array):
    {
        "Name": "...",
        "BirthYear": 1947, "BirthMonth": 8, "BirthDay": 15,
        "BirthHour": 0, "BirthMinute": 1,
        "BirthLocation": "New Delhi, India",
        "Notes": "First PM of independent India. ...",
        "Tags": ["politician", "leadership"]
    }

Run with:
    make ingest-cases
    uv run python scripts/ingest_vedastro.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


RAW_DIR   = Path("data/raw/vedastro")
OUT_PATH  = RAW_DIR / "cases.json"


def normalise_entry(raw: dict) -> dict | None:
    """Convert a VedAstro record to our internal case format."""
    try:
        year   = int(raw.get("BirthYear",   raw.get("year",   0)))
        month  = int(raw.get("BirthMonth",  raw.get("month",  0)))
        day    = int(raw.get("BirthDay",    raw.get("day",    0)))
        hour   = int(raw.get("BirthHour",   raw.get("hour",   0)))
        minute = int(raw.get("BirthMinute", raw.get("minute", 0)))
        place  = raw.get("BirthLocation", raw.get("place", ""))
        notes  = raw.get("Notes",   raw.get("notes", ""))
        name   = raw.get("Name",    raw.get("name",  "Unknown"))
        tags   = raw.get("Tags",    raw.get("tags",  []))
    except (TypeError, ValueError):
        return None

    if not all([year, month, day, place]):
        return None

    return {
        "name": name,
        "year": year, "month": month, "day": day,
        "hour": hour, "minute": minute,
        "place": place,
        "notes": notes,
        "tags": tags,
        "summary": f"{name} ({year}): {notes[:200]}".strip(),
        # These fields are populated after chart computation (optional)
        "lagna_sign": None,
        "moon_sign": None,
    }


def main() -> None:
    if not RAW_DIR.exists():
        print(f"VedAstro data directory not found: {RAW_DIR}")
        print("Place VedAstro JSON exports in data/raw/vedastro/")
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text("[]")
        return

    json_files = list(RAW_DIR.glob("*.json"))
    json_files = [f for f in json_files if f.name != "cases.json"]

    if not json_files:
        print(f"No JSON files found in {RAW_DIR}")
        OUT_PATH.write_text("[]")
        return

    cases = []
    skipped = 0

    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  SKIP {path.name}: JSON parse error — {exc}")
            continue

        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            case = normalise_entry(entry)
            if case:
                cases.append(case)
            else:
                skipped += 1

        print(f"  {path.name}: {len(entries)} entries processed")

    OUT_PATH.write_text(json.dumps(cases, indent=2, ensure_ascii=False))
    print(f"\nTotal: {len(cases)} cases → {OUT_PATH} ({skipped} skipped)")


if __name__ == "__main__":
    main()
