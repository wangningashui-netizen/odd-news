#!/usr/bin/env python3
"""The untranslated export covers the recent window, not only the newest day."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import export_untranslated


def story(item_id: str, status: str, source: str = "News18 Viral") -> dict:
    return {
        "id": item_id,
        "title_en": f"Title {item_id}",
        "summary_en": f"Summary {item_id}",
        "title_zh": "" if status == "pending" else "已有译文",
        "summary_zh": "",
        "translation_status": status,
        "url": f"https://example.com/{item_id}",
        "source": source,
    }


class ExportUntranslatedTest(unittest.TestCase):
    def test_window_rewrites_recent_days_and_clears_finished_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            days = {
                "2026-11-16": [story("old", "pending")],
                "2026-11-18": [story("keep", "fallback", "NDTV Offbeat")],
                "2026-11-22": [story("done", "ai")],
                "2026-11-24": [story("fresh", "pending", "Times Now Viral")],
            }
            stale = data / "untranslated" / "2026-11-22.json"
            stale.parent.mkdir(parents=True)
            stale.write_text('{"date": "2026-11-22", "items": [{"id": "stale"}]}\n', encoding="utf-8")
            outside = data / "untranslated" / "2026-11-16.json"
            outside.write_text('{"date": "2026-11-16", "items": [{"id": "leave"}]}\n', encoding="utf-8")

            export_untranslated.write_latest(data, days)

            latest = json.loads((data / "untranslated" / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["date"], "2026-11-24")
            self.assertEqual([row["id"] for row in latest["items"]], ["fresh"])
            self.assertEqual(
                set(latest["items"][0]),
                {
                    "id",
                    "title_en",
                    "summary_en",
                    "title_zh",
                    "summary_zh",
                    "translation_status",
                    "url",
                    "source",
                },
            )
            dated = json.loads((data / "untranslated" / "2026-11-24.json").read_text(encoding="utf-8"))
            self.assertEqual(dated, latest)
            kept = json.loads((data / "untranslated" / "2026-11-18.json").read_text(encoding="utf-8"))
            self.assertEqual([row["id"] for row in kept["items"]], ["keep"])
            self.assertEqual(kept["items"][0]["translation_status"], "fallback")
            cleared = json.loads((data / "untranslated" / "2026-11-22.json").read_text(encoding="utf-8"))
            self.assertEqual(cleared, {"date": "2026-11-22", "items": []})
            self.assertFalse((data / "untranslated" / "2026-11-23.json").exists())
            self.assertEqual(
                outside.read_text(encoding="utf-8"),
                '{"date": "2026-11-16", "items": [{"id": "leave"}]}\n',
            )

    def test_dry_run_prints_files_and_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            days = {
                "2026-11-20": [story("backlog", "pending")],
                "2026-11-24": [story("today", "fallback")],
            }
            export_untranslated.write_latest(data, days, dry_run=True)
            self.assertFalse((data / "untranslated").exists())


if __name__ == "__main__":
    unittest.main()
