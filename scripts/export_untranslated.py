#!/usr/bin/env python3
"""Write items that still need a committed translation.

``data/untranslated/latest.json`` lists every item on the newest day whose
``translation_status`` is ``fallback`` (machine translation, shown as 机翻)
or ``pending`` (no Chinese yet). The same list is also written to
``data/untranslated/YYYY-MM-DD.json``. The live site serves the first file at
``data/untranslated/latest.json``.

The daily fetch only sees part of a calendar day. The rest arrives on the next
run and is filed under the previous date, so each run also rewrites the dated
file for the newest day and the six days before it. A day in that window with
nothing left to translate is cleared to an empty list. Older files are left
alone. ``latest.json`` is still only the newest day, with the same fields.

Each row has ``id``, ``title_en``, ``summary_en``, the current ``title_zh``
and ``summary_zh``, plus ``translation_status``, ``url`` and ``source``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import fetch_news

# Matches the fetch retry window: a story is still in play for seven days.
WINDOW_DAYS = 7


def fallback_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        if item.get("translation_status") not in {"fallback", "pending"}:
            continue
        if not item.get("id"):
            continue
        rows.append(
            {
                "id": item["id"],
                "title_en": item.get("title_en") or "",
                "summary_en": item.get("summary_en") or "",
                "title_zh": item.get("title_zh") or "",
                "summary_zh": item.get("summary_zh") or "",
                "translation_status": item.get("translation_status") or "",
                "url": item.get("url") or "",
                "source": item.get("source") or "",
            }
        )
    rows.sort(key=lambda row: (row["source"], row["id"]))
    return rows


def dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_if_changed(path: Path, payload: dict) -> bool:
    text = dump(payload)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def newest_date(days: dict[str, list[dict]]) -> str | None:
    dates = sorted(day for day, items in days.items() if items)
    return dates[-1] if dates else None


def window_dates(newest: str, days: dict[str, list[dict]]) -> list[str]:
    anchor = datetime.strptime(newest, "%Y-%m-%d").date()
    start = anchor - timedelta(days=WINDOW_DAYS - 1)
    found: list[str] = []
    for key, items in days.items():
        if not items:
            continue
        try:
            current = datetime.strptime(key, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start <= current <= anchor:
            found.append(key)
    return sorted(found)


def day_payload(date: str, items: list[dict]) -> dict:
    return {"date": date, "items": fallback_rows(items)}


def write_latest(data: Path, days: dict[str, list[dict]], *, dry_run: bool = False) -> bool:
    """Refresh latest.json and the dated files in the recent window.

    ``dry_run`` prints the files that would be written and does not touch disk.
    The return value is whether a real write changed a file.
    """
    date = newest_date(days)
    prefix = "dry-run " if dry_run else ""
    if not date:
        payload = {"date": "", "items": []}
        print(f"{prefix}untranslated none count=0", flush=True)
        if dry_run:
            print(f"{prefix}untranslated file data/untranslated/latest.json count=0", flush=True)
            return False
        return write_if_changed(data / "untranslated" / "latest.json", payload)

    changed = False
    payloads = [(day, day_payload(day, days.get(day) or [])) for day in window_dates(date, days)]
    # The historical log line is the newest day. Dated files follow, newest first
    # in that line and then the rest of the window in calendar order.
    by_date = dict(payloads)
    latest = by_date.get(date) or day_payload(date, [])
    print(f"{prefix}untranslated {date} count={len(latest['items'])}", flush=True)
    print(
        f"{prefix}untranslated file data/untranslated/latest.json "
        f"date={latest['date']} count={len(latest['items'])}",
        flush=True,
    )
    directory = data / "untranslated"
    for day, payload in payloads:
        path = directory / f"{day}.json"
        if day != date and not payload["items"] and not path.exists():
            continue
        print(
            f"{prefix}untranslated file data/untranslated/{day}.json count={len(payload['items'])}",
            flush=True,
        )
        if dry_run:
            continue
        if day == date and write_if_changed(directory / "latest.json", payload):
            changed = True
        if write_if_changed(path, payload):
            changed = True
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Export items that still need a translation")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the untranslated files that would be written, without changing them",
    )
    args = parser.parse_args()
    days = fetch_news.load_days()
    write_latest(fetch_news.DATA, days, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
