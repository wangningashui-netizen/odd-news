#!/usr/bin/env python3
"""Machine translation retries rate limits and does not drop a whole batch."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

import fetch_news


def http_error(code: int) -> urllib.error.HTTPError:
    message = "Too Many Requests" if code == 429 else "Error"
    return urllib.error.HTTPError(
        "https://translate.googleapis.com/",
        code,
        message,
        hdrs=None,
        fp=io.BytesIO(b""),
    )


class Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


def translated(*parts: str) -> bytes:
    joined = fetch_news.TRANSLATE_SEP.join(parts)
    return json.dumps([[[joined, None]]]).encode()


class TranslateFallbackTest(unittest.TestCase):
    def test_retries_429_with_backoff_then_succeeds(self) -> None:
        calls = {"n": 0}
        sleeps: list[float] = []

        def urlopen(request, timeout=30, context=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise http_error(429)
            return Response(translated("标题", "概要"))

        fetch_news.gtranslate_many(
            ["Title", "Summary"],
            budget=fetch_news.TranslateBudget(90),
            urlopen=urlopen,
            sleep=sleeps.append,
        )
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(calls["n"], 3)

    def test_wait_budget_stops_retries(self) -> None:
        sleeps: list[float] = []

        def urlopen(request, timeout=30, context=None):
            raise http_error(503)

        budget = fetch_news.TranslateBudget(3)
        with self.assertRaises(urllib.error.HTTPError):
            fetch_news.gtranslate_many(
                ["Title"],
                budget=budget,
                urlopen=urlopen,
                sleep=sleeps.append,
            )
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertTrue(budget.exhausted)
        self.assertLessEqual(sum(sleeps), 3)

    def test_one_item_failure_does_not_drop_the_rest(self) -> None:
        def urlopen(request, timeout=30, context=None):
            query = request.full_url
            if "FIRST" in query and "SECOND" in query:
                raise http_error(400)
            if "FIRST" in query:
                raise http_error(400)
            return Response(translated("第二条标题", "第二条概要"))

        items = [
            {
                "id": "1",
                "title_en": "FIRST story",
                "summary_en": "FIRST summary",
                "title_zh": "",
                "translation_status": "pending",
            },
            {
                "id": "2",
                "title_en": "SECOND story",
                "summary_en": "SECOND summary",
                "title_zh": "",
                "translation_status": "pending",
            },
        ]
        fetch_news.fallback_translate(items, urlopen=urlopen, sleep=lambda _delay: None)
        self.assertFalse(items[0].get("title_zh"))
        self.assertEqual(items[0]["translation_status"], "pending")
        self.assertEqual(items[1]["title_zh"], "第二条标题")
        self.assertEqual(items[1]["summary_zh"], "第二条概要")
        self.assertEqual(items[1]["translation_status"], "fallback")

    def test_plain_ok_does_not_enable_the_model_path(self) -> None:
        def post_json(url, payload, headers, timeout=60):
            return 200, "text/plain", "OK\r\n"

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
            with mock.patch.object(fetch_news, "post_json", post_json):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    self.assertFalse(fetch_news.probe_models())
        self.assertIn("not a chat completion", stdout.getvalue())
        self.assertIn("Skipping the model path", stdout.getvalue())

    def test_chat_completion_enables_the_model_path(self) -> None:
        def post_json(url, payload, headers, timeout=60):
            return 200, "application/json", '{"choices":[{"message":{"content":"pong"}}]}'

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
            with mock.patch.object(fetch_news, "post_json", post_json):
                self.assertTrue(fetch_news.probe_models())


if __name__ == "__main__":
    unittest.main()
