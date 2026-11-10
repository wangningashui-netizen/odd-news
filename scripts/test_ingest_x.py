#!/usr/bin/env python3
"""Inbox normalization, site ids, India filter, and X fields on the search export."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import fetch_news
import ingest_x
import render_comments
import reply_filter
import x_targets


def raw_trial_post() -> dict:
    return {
        "id": "2118",
        "url": "https://x.com/PressSecretary7/status/2118250999898882303",
        "author": {
            "name": "The Press Secretary",
            "username": "PressSecretary7",
            "avatar_url": "https://pbs.twimg.com/profile_images/x_normal.jpg",
            "verified": True,
        },
        "created_at": "2026-11-05T07:56:08.000Z",
        "text": "Indian police wrestle a giant rat.",
        "public_metrics": {
            "reply_count": 7,
            "repost_count": 3,
            "like_count": 4,
            "quote_count": 0,
            "bookmark_count": 0,
            "impression_count": 1791,
        },
        "photos": [],
        "video": {
            "has_video": True,
            "meta": {
                "preview_image_url": "https://pbs.twimg.com/amplify_video_thumb/x.jpg",
                "best_variant_url": "https://video.twimg.com/amplify_video/x.mp4",
            },
        },
        "summary_zh": "印度警察街头用绳子制服巨型大鼠。",
        "replies": [
            {
                "id": "child",
                "text": "nested",
                "created_at": "2026-11-05T13:16:55.000Z",
                "author": {"name": "Press", "username": "PressSecretary7", "avatar_url": "", "verified": False},
                "public_metrics": {"reply": 0, "retweet": 0, "like": 0, "view": 38},
                "referenced_tweets": [{"id": "parent", "type": "replied_to"}],
            },
            {
                "id": "low",
                "text": "few likes",
                "created_at": "2026-11-05T12:00:00.000Z",
                "author": {"name": "A", "username": "a", "verified": False},
                "public_metrics": {"like": 1, "view": 10},
                "referenced_tweets": [{"id": "2118", "type": "replied_to"}],
            },
            {
                "id": "parent",
                "text": "more likes",
                "created_at": "2026-11-05T12:10:00.000Z",
                "author": {"name": "B", "username": "b", "verified": True},
                "public_metrics": {"like": 5, "reply": 1, "view": 20},
                "referenced_tweets": [{"id": "2118", "type": "replied_to"}],
            },
        ],
    }


class InboxTests(unittest.TestCase):
    def test_site_id_matches_the_translation_key(self) -> None:
        url = "https://x.com/PressSecretary7/status/2118250999898882303"
        expected = hashlib.sha1(fetch_news.dedupe_key(url).encode("utf-8")).hexdigest()[:16]
        self.assertEqual(ingest_x.site_id(url), expected)
        self.assertEqual(len(expected), 16)

    def test_normalize_trial_shape(self) -> None:
        post = ingest_x.normalize_post(raw_trial_post())
        self.assertEqual(post["public_metrics"]["like_count"], 4)
        self.assertEqual(post["public_metrics"]["impression_count"], 1791)
        self.assertTrue(post["has_video"])
        self.assertEqual(post["video_thumbnail"], "https://pbs.twimg.com/amplify_video_thumb/x.jpg")
        self.assertEqual(post["video_direct_url"], "https://video.twimg.com/amplify_video/x.mp4")
        self.assertEqual(post["summary_zh"], "印度警察街头用绳子制服巨型大鼠。")
        child = next(reply for reply in post["replies"] if reply["id"] == "child")
        self.assertEqual(child["in_reply_to_id"], "parent")
        self.assertEqual(child["public_metrics"]["impression_count"], 38)
        self.assertNotIn("quote_count", child["public_metrics"])

    def test_replies_sort_by_likes_and_nest(self) -> None:
        post = ingest_x.normalize_post(raw_trial_post())
        ordered = render_comments.order_replies(post["replies"])
        ids = [reply["id"] for reply, _above, _below in ordered]
        self.assertEqual(ids, ["parent", "child", "low"])
        self.assertEqual(ordered[1][1], True)

    def test_purge_uses_content_region_and_keeps_x(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            old = fetch_news.DATA
            fetch_news.DATA = data
            try:
                day = data / "2026-11-08.json"
                day.write_text("{}", encoding="utf-8")
                days = {
                    "2026-11-08": [
                        {"id": "india", "region": "印度", "source": "Oddity Central"},
                        {"id": "foreign", "region": "中国", "source": "Times Now Viral", "source_region": "印度"},
                        {"id": "xpost", "kind": "x", "region": "美国"},
                    ]
                }
                fetch_news.purge_non_india(days)
                self.assertEqual([item["id"] for item in days["2026-11-08"]], ["india", "xpost"])
                self.assertTrue(day.exists())
                days["2026-11-08"] = [item for item in days["2026-11-08"] if item["id"] != "india" and item["kind"] != "x"]
                # The row above drops both keepers; force an empty day through the filter.
                days["2026-11-08"] = [{"id": "foreign2", "region": "英国", "source": "NDTV Offbeat"}]
                fetch_news.purge_non_india(days)
                self.assertNotIn("2026-11-08", days)
                self.assertFalse(day.exists())
            finally:
                fetch_news.DATA = old

    def test_search_export_keeps_x_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            old = fetch_news.DATA
            fetch_news.DATA = data
            try:
                days = {
                    "2026-11-10": [
                        {
                            "id": "abc",
                            "published_at": "2026-11-10T12:00:00+08:00",
                            "title_zh": "标题",
                            "title_en": "title",
                            "summary_zh": "概要",
                            "summary_en": "full text",
                            "image": "https://wangningashui-netizen.github.io/odd-news/assets/x/1/video-thumb.jpg",
                            "source": "X",
                            "region": "印度",
                            "tags": ["动物"],
                            "url": "https://x.com/a/status/1",
                            "translation_status": "ai",
                            "kind": "x",
                            "x": {
                                "post_url": "https://x.com/a/status/1",
                                "ytdlp_command": "yt-dlp https://x.com/a/status/1",
                                "video_url": "https://video.twimg.com/a.mp4",
                                "comments_image": "https://wangningashui-netizen.github.io/odd-news/assets/x/1/comments.png",
                                "photos": ["https://wangningashui-netizen.github.io/odd-news/assets/x/1/photo-1.jpg"],
                                "text": "full text",
                            },
                        }
                    ]
                }
                fetch_news.write_search(days)
                saved = json.loads((data / "search" / "2026-11.json").read_text(encoding="utf-8"))
                row = saved["items"][0]
                self.assertEqual(row["kind"], "x")
                self.assertEqual(row["x"]["ytdlp_command"], "yt-dlp https://x.com/a/status/1")
                self.assertTrue(row["x"]["comments_image"].startswith("https://wangningashui-netizen.github.io/odd-news/"))
                self.assertEqual(row["region"], "印度")
                self.assertTrue((data / "search-index.json").exists())
            finally:
                fetch_news.DATA = old

    def test_optional_angle_and_reply_filter(self) -> None:
        bare = ingest_x.normalize_post(raw_trial_post())
        self.assertNotIn("angle", bare)
        flagged = dict(raw_trial_post())
        flagged["angle"] = "official"
        self.assertEqual(ingest_x.normalize_post(flagged)["angle"], "official")
        self.assertEqual(x_targets.infer_angle("Indian police wrestle a giant rat", "PressSecretary7"), "离谱")
        self.assertEqual(x_targets.infer_angle("Petroleum ministry defends E20 petrol", "someguy"), "官方")
        self.assertEqual(x_targets.infer_angle("a cobra under the carpet", "narendramodi"), "官方")
        self.assertTrue(reply_filter.reply_excluded(
            "@AsianDigest Indians as soon as they see an air-plane (the think it is a deamon or so..)"
        ))
        self.assertTrue(reply_filter.reply_excluded(
            'Or, as India would tell the story, "The clever and sneaky plane ruined the Diwali."'
        ))
        self.assertFalse(reply_filter.reply_excluded("@PressSecretary7 @grok Master Splinter?"))
        self.assertFalse(reply_filter.reply_excluded("@AsianDigest I didn’t know Budweiser was in India"))
        kept, removed = reply_filter.filter_replies(
            [{"text": "Master Splinter?"}, {"text": "Indians as soon as they see a plane"}]
        )
        self.assertEqual(removed, 1)
        self.assertEqual(len(kept), 1)

    def test_reddit_stats_match_archive_posts_without_inventing_zeros(self) -> None:
        self.assertEqual(
            fetch_news.reddit_base_id({"url": "https://www.reddit.com/r/india/comments/1xqyf47/hello/"}),
            "1xqyf47",
        )
        self.assertEqual(fetch_news.reddit_base_id({"reddit_id": "t3_AbC123"}), "abc123")
        item = {
            "source": "Reddit r/india",
            "url": "https://example.com/story?utm_source=reddit",
            "reddit_score": None,
        }
        untouched = {
            "source": "Reddit r/india",
            "url": "https://example.com/other",
            "reddit_score": 4,
            "reddit_comments": 1,
        }
        changed = fetch_news.apply_reddit_posts(
            [item, untouched],
            [{
                "id": "zzz",
                "score": 12,
                "num_comments": 3,
                "url": "https://www.example.com/story",
                "name": "t3_zzz",
            }],
        )
        self.assertEqual(changed, 1)
        self.assertEqual(item["reddit_score"], 12)
        self.assertEqual(item["reddit_comments"], 3)
        self.assertEqual(item["reddit_id"], "t3_zzz")
        self.assertEqual(untouched["reddit_score"], 4)
        self.assertIsNone(fetch_news._stat_tuple({"id": "x", "score": None, "num_comments": None}))


if __name__ == "__main__":
    unittest.main()
