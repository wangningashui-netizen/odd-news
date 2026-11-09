#!/usr/bin/env python3
"""Apply committed Chinese translations and rebuild the site indexes.

Reads every ``data/translations/YYYY-MM-DD.json`` file. Each file is a map of
item id to ``{"title_zh", "summary_zh"}``. The id is the ``id`` field already
stored on each story (first 16 hex chars of the sha1 of the normalized URL).
A translation matches that id on any day, not only the day in the file name.

Applied items get ``translation_status`` ``ai``, which removes the 机翻 badge.
Running this again with the same files changes nothing.

Also refreshes ``data/untranslated/latest.json`` so the latest day's remaining
machine translations are listed for the next pass.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fetch_news

DATE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def translation_dir(data: Path) -> Path:
    return data / "translations"


def load_translation_map(directory: Path) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    if not directory.is_dir():
        return mapping
    files = sorted(path for path in directory.glob("*.json") if DATE_NAME.match(path.name))
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"skip {path.name}: {exc}", flush=True)
            continue
        if not isinstance(payload, dict):
            print(f"skip {path.name}: expected an object keyed by item id", flush=True)
            continue
        for item_id, fields in payload.items():
            if not isinstance(fields, dict):
                continue
            title = str(fields.get("title_zh") or "").strip()
            summary = str(fields.get("summary_zh") or "").strip()
            if not item_id or not title or not summary:
                print(f"skip {item_id or '?'} in {path.name}: title_zh and summary_zh are required", flush=True)
                continue
            mapping[str(item_id)] = {"title_zh": title, "summary_zh": summary}
    return mapping


def ensure_ids(days: dict[str, list[dict]]) -> set[str]:
    dirty: set[str] = set()
    for date, items in days.items():
        for item in items:
            if item.get("id"):
                continue
            url = item.get("url") or ""
            if not url:
                continue
            item["id"] = fetch_news.hashlib.sha1(fetch_news.dedupe_key(url).encode("utf-8")).hexdigest()[:16]
            dirty.add(date)
    return dirty


def apply_map(days: dict[str, list[dict]], mapping: dict[str, dict[str, str]]) -> tuple[int, set[str], list[str]]:
    by_id: dict[str, list[tuple[str, dict]]] = {}
    for date, items in days.items():
        for item in items:
            item_id = str(item.get("id") or "")
            if item_id:
                by_id.setdefault(item_id, []).append((date, item))
    changed = 0
    dirty: set[str] = set()
    missing: list[str] = []
    for item_id, fields in mapping.items():
        hits = by_id.get(item_id)
        if not hits:
            missing.append(item_id)
            continue
        for date, item in hits:
            if (
                item.get("title_zh") == fields["title_zh"]
                and item.get("summary_zh") == fields["summary_zh"]
                and item.get("translation_status") == "ai"
            ):
                continue
            item["title_zh"] = fields["title_zh"]
            item["summary_zh"] = fields["summary_zh"]
            item["translation_status"] = "ai"
            dirty.add(date)
            changed += 1
    return changed, dirty, missing


def run(root: Path | None = None) -> int:
    root = (root or fetch_news.ROOT).resolve()
    data = root / "data"
    previous = fetch_news.DATA
    fetch_news.DATA = data
    try:
        days = fetch_news.load_days()
        dirty = ensure_ids(days)
        mapping = load_translation_map(translation_dir(data))
        changed, applied, missing = apply_map(days, mapping)
        dirty |= applied
        if dirty:
            fetch_news.write_outputs(days, dirty)
        import export_untranslated

        export_untranslated.write_latest(data, days)
    finally:
        fetch_news.DATA = previous
    print(
        f"translations={len(mapping)} updated={changed} missing={len(missing)} days={len(dirty)}",
        flush=True,
    )
    for item_id in missing[:20]:
        print(f"  no item with id {item_id}", flush=True)
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
