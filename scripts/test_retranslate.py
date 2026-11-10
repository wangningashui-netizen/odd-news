#!/usr/bin/env python3
"""Prove committed translations apply by id, across dates, and only once."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import retranslate


def day(date: str, items: list[dict]) -> dict:
    return {"date": date, "timezone": "Asia/Shanghai", "count": len(items), "items": items}


class ApplyTranslationsTest(unittest.TestCase):
    def test_apply_is_idempotent_and_matches_any_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            (data / "translations").mkdir(parents=True)
            story = {
                "id": "abc123",
                "url": "https://example.com/train",
                "title_en": "CEO takes the train",
                "summary_en": "He saved money and arrived late.",
                "title_zh": "首席执行官坐火车",
                "summary_zh": "首席执行官坐火车",
                "translation_status": "fallback",
                "source": "NDTV Offbeat",
                "region": "印度",
                "published_at": "2026-11-08T14:00:00+08:00",
                "tags": ["交通火车"],
            }
            waiting = {
                "id": "needzh",
                "url": "https://example.com/waiting",
                "title_en": "Still in English",
                "summary_en": "No Chinese yet.",
                "title_zh": None,
                "summary_zh": None,
                "translation_status": "pending",
                "source": "News18 Viral",
                "region": "印度",
                "published_at": "2026-11-08T15:00:00+08:00",
                "tags": ["其他"],
            }
            other_day = {
                "id": "keepme",
                "url": "https://example.com/other",
                "title_en": "Already done",
                "summary_en": "Leave this alone.",
                "title_zh": "已经译好",
                "summary_zh": "这条不要动。",
                "translation_status": "ai",
                "source": "Oddity Central",
                "region": "全球",
                "published_at": "2026-11-07T09:00:00+08:00",
                "tags": ["其他"],
            }
            (data / "2026-11-08.json").write_text(
                json.dumps(day("2026-11-08", [story, waiting]), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (data / "2026-11-07.json").write_text(
                json.dumps(day("2026-11-07", [other_day]), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            # File date is not the item's date. Match is by id.
            (data / "translations" / "2026-11-09.json").write_text(
                json.dumps(
                    {
                        "abc123": {
                            "title_zh": "首席执行官改坐火车",
                            "summary_zh": "他为了省钱改坐火车，结果晚点到达。",
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(retranslate.run(root), 0)
            saved = json.loads((data / "2026-11-08.json").read_text(encoding="utf-8"))
            item = next(row for row in saved["items"] if row["id"] == "abc123")
            self.assertEqual(item["translation_status"], "ai")
            self.assertEqual(item["title_zh"], "首席执行官改坐火车")
            self.assertEqual(item["summary_zh"], "他为了省钱改坐火车，结果晚点到达。")
            untouched = json.loads((data / "2026-11-07.json").read_text(encoding="utf-8"))["items"][0]
            self.assertEqual(untouched["title_zh"], "已经译好")
            self.assertEqual(untouched["translation_status"], "ai")
            index = json.loads((data / "index.json").read_text(encoding="utf-8"))
            self.assertEqual([row["date"] for row in index["dates"]], ["2026-11-08", "2026-11-07"])
            self.assertTrue((data / "search-index.json").exists())
            listed = json.loads((data / "untranslated" / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(listed["date"], "2026-11-08")
            self.assertEqual([row["id"] for row in listed["items"]], ["needzh"])
            self.assertEqual(listed["items"][0]["translation_status"], "pending")
            before = (data / "2026-11-08.json").read_text(encoding="utf-8")
            index_before = (data / "index.json").read_text(encoding="utf-8")
            self.assertEqual(retranslate.run(root), 0)
            self.assertEqual((data / "2026-11-08.json").read_text(encoding="utf-8"), before)
            self.assertEqual((data / "index.json").read_text(encoding="utf-8"), index_before)

    def test_title_applies_when_summary_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            (data / "translations").mkdir(parents=True)
            story = {
                "id": "titleonly",
                "url": "https://example.com/airport",
                "title_en": "Ceiling collapse",
                "summary_en": "A visitor was injured.",
                "title_zh": "旧标题",
                "summary_zh": "原来的概要还在。",
                "translation_status": "fallback",
                "source": "Indian Express Trending",
                "region": "印度",
                "published_at": "2026-11-09T10:00:00+08:00",
                "tags": ["其他"],
            }
            (data / "2026-11-09.json").write_text(
                json.dumps(day("2026-11-09", [story]), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (data / "translations" / "2026-11-10.json").write_text(
                json.dumps(
                    {"titleonly": {"title_zh": "孟买机场吊顶坍塌", "summary_zh": ""}},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(retranslate.run(root), 0)
            saved = json.loads((data / "2026-11-09.json").read_text(encoding="utf-8"))
            item = saved["items"][0]
            self.assertEqual(item["title_zh"], "孟买机场吊顶坍塌")
            self.assertEqual(item["summary_zh"], "原来的概要还在。")
            self.assertEqual(item["translation_status"], "ai")


if __name__ == "__main__":
    unittest.main()
