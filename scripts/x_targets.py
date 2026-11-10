"""Official-vs-oddity angle for X posts.

The collector outside this repo reads ``data/x/targets.json`` and searches
those keywords and accounts. Ingest does not call X. When an inbox post
omits ``angle``, the same file decides the tag: an account or keyword hit
is ``官方``; everything else is ``离谱``. An inbox ``angle`` is kept.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS_PATH = ROOT / "data" / "x" / "targets.json"

OFFICIAL = "官方"
ODDITY = "离谱"

_OFFICIAL_WORDS = {"官方", "official", "gov", "government"}
_ODDITY_WORDS = {"离谱", "oddity", "oddities", "viral"}


def normalize_angle(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if text in _OFFICIAL_WORDS or lowered in _OFFICIAL_WORDS:
        return OFFICIAL
    if text in _ODDITY_WORDS or lowered in _ODDITY_WORDS:
        return ODDITY
    return None


@lru_cache(maxsize=1)
def load_targets() -> dict:
    payload = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("data/x/targets.json must be an object")
    return payload


def keywords() -> list[str]:
    rows = load_targets().get("keywords") or []
    found: list[str] = []
    for row in rows:
        if isinstance(row, str) and row.strip():
            found.append(row.strip())
        elif isinstance(row, dict) and str(row.get("text") or "").strip():
            found.append(str(row["text"]).strip())
    return found


def verified_handles() -> set[str]:
    found: set[str] = set()
    for row in load_targets().get("accounts") or []:
        if not isinstance(row, dict):
            continue
        if row.get("verified") is not True:
            continue
        handle = str(row.get("handle") or "").strip().lstrip("@")
        if handle:
            found.add(handle.lower())
    return found


def _keyword_hit(keyword: str, lowered: str) -> bool:
    needle = keyword.lower()
    if re.search(r"[a-z0-9]", needle) and " " not in needle and not re.search(r"[^\x00-\x7f]", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lowered) is not None
    return needle in lowered


def keyword_matches(text: str) -> bool:
    lowered = (text or "").lower()
    return any(_keyword_hit(keyword, lowered) for keyword in keywords())


def handle_matches(username: str) -> bool:
    handle = (username or "").strip().lstrip("@").lower()
    return bool(handle) and handle in verified_handles()


def infer_angle(text: str, username: str = "") -> str:
    if handle_matches(username) or keyword_matches(text):
        return OFFICIAL
    return ODDITY


def assign_angle(item: dict, inbox_angle: str | None = None) -> None:
    """Set ``item['x'].angle``. An inbox value wins over inference."""
    extra = item.setdefault("x", {})
    chosen = normalize_angle(inbox_angle)
    if chosen:
        extra["angle"] = chosen
        extra["angle_source"] = "inbox"
        return
    if extra.get("angle_source") == "inbox":
        kept = normalize_angle(extra.get("angle"))
        if kept:
            extra["angle"] = kept
            return
    author = extra.get("author") or {}
    text = " ".join(
        part
        for part in (
            item.get("title_en"),
            item.get("summary_en"),
            item.get("title_zh"),
            item.get("summary_zh"),
            extra.get("text"),
        )
        if part
    )
    extra["angle"] = infer_angle(text, str(author.get("username") or ""))
    extra["angle_source"] = "inferred"
