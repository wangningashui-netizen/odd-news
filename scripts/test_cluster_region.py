#!/usr/bin/env python3
"""Spot-checks for story clustering and content-based regions."""

from __future__ import annotations

import unittest

from cluster_items import cluster_items
from content_region import classify_region


def story(title, summary="", day="2026-11-07", source="News18 Viral", region="印度"):
    return {
        "id": title[:12].replace(" ", ""),
        "title_en": title,
        "summary_en": summary,
        "published_at": day + "T10:00:00+08:00",
        "source": source,
        "region": region,
    }


class ClusterTests(unittest.TestCase):
    def test_ethanol_stories_join_and_jobs_do_not(self) -> None:
        items = [
            story("E20 fuel row in Karnataka after 31% ethanol claim", "Oil firms reject the 31% figure.", "2026-11-06"),
            story("Lab tests show ethanol blend in petrol as high as 31%", "Samples from Karnataka.", "2026-11-07"),
            story("Petroleum ministry disputes excess ethanol in petrol", "Tests stayed near 20%.", "2026-11-08"),
            story("E30 petrol being sold as E20 in Karnataka", "Test data from pumps.", "2026-11-06", source="Reddit r/india"),
            story("Indian man torn between Rs 45 LPA job and Germany", "He fears layoffs.", "2026-11-08"),
            story("IIM graduate quits Rs 37 LPA startup job", "He left after six months.", "2026-11-08"),
            story("Happy Diwali everyone", "Have a good evening.", "2026-11-08"),
            story("Happy Diwali", "Eat sweets.", "2026-11-08"),
        ]
        groups = cluster_items(items)
        ethanol = [group for group in groups if any("ethanol" in item["title_en"].lower() or "e20" in item["title_en"].lower() for item in group)]
        self.assertEqual(len(ethanol), 1)
        self.assertEqual(len(ethanol[0]), 4)
        jobs = [group for group in groups if any("LPA" in item["title_en"] for item in group)]
        self.assertEqual(len(jobs), 2)
        diwali = [group for group in groups if any(item["title_en"].startswith("Happy") for item in group)]
        self.assertTrue(all(len(group) == 1 for group in diwali))

    def test_region_follows_the_story_not_the_publisher(self) -> None:
        self.assertEqual(
            classify_region("Seattle man wins the state lottery", "The drawing was held in Washington.", "印度"),
            "美国",
        )
        self.assertEqual(
            classify_region("Pani puri seller in Mumbai earns Rs 1.2 lakh", "One stall, evenings only.", "全球"),
            "印度",
        )
        self.assertEqual(
            classify_region("A quiet note about clouds", "No place is mentioned.", "日本"),
            "日本",
        )
        self.assertEqual(
            classify_region(
                "Woman finds a disturbing VHS tape",
                "The house is in Maine and the doll was a Barbie.",
                "美国",
            ),
            "美国",
        )


if __name__ == "__main__":
    unittest.main()
