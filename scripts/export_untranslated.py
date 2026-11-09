#!/usr/bin/env python3
"""Write the latest day's items that still need a committed translation.

``data/untranslated/latest.json`` lists every item on the newest day whose
``translation_status`` is ``fallback`` (machine translation, shown as 机翻)
or ``pending`` (no Chinese yet). The same list is also written to
``data/untranslated/YYYY-MM-DD.json``. The live site serves the first file at
``data/untranslated/latest.json``.

Each row has ``id``, ``title_en``, ``summary_en``, the current ``title_zh``
and ``summary_zh``, plus ``translation_status``, ``url`` and ``source``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import fetch_news


def newest_date(days: dict[str, list[dict]]) -> str | None:
    dates = sorted(day for day, items in days.items() if items)
    return dates[-1] if dates else None


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


def write_latest(data: Path, days: dict[str, list[dict]]) -> bool:
    date = newest_date(days)
    payload = {"date": date or "", "items": fallback_rows(days.get(date, []) if date else [])}
    changed = write_if_changed(data / "untranslated" / "latest.json", payload)
    if date:
        changed = write_if_changed(data / "untranslated" / f"{date}.json", payload) or changed
    print(f"untranslated {date or 'none'} count={len(payload['items'])}", flush=True)
    return changed


def main() -> int:
    days = fetch_news.load_days()
    write_latest(fetch_news.DATA, days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
