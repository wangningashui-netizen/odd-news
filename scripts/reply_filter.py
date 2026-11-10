"""Drop replies that should not appear on a rendered comment sheet.

The sheet is a layout of real replies, not a screenshot, and it is posted
with short videos. A reply is removed when it demeans a nationality,
ethnicity, religion, or caste, uses a slur for one of those groups, or
repeats a generic ethnic stereotype. Rude replies that argue with a named
person, a media outlet, or the video itself stay, including jokes that are
not about a people (a rat called Splinter, a beer brand, a measurement).

The collector is expected to pre-filter too. This module still runs at
render time so an older inbox file cannot put those replies on the image.
Filtering is conservative: a clear group attack is removed; an unclear
political complaint about a named official is kept.

``FILTER_VERSION`` is mixed into the X content hash so a change here
re-renders sheets on the next ingest.
"""

from __future__ import annotations

import re

FILTER_VERSION = "1"

COMMENTS_IMAGE_NOTE = "根据真实回复渲染的评论区，不是 X 的截图。"

# Word-boundary slurs and coded group insults. Generic swearing at one
# person or at a newsroom is intentionally not in this list.
_SLUR_RES = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bpajeets?\b",
        r"\bpoojeets?\b",
        r"\bstreet[\s-]?shitters?\b",
        r"\bshit[\s-]?skins?\b",
        r"\bchinks?\b",
        r"\bchink(?:i|y|ies)\b",
        r"\bniggers?\b",
        r"\bniggas?\b",
        r"\bkikes?\b",
        r"\bspics?\b",
        r"\bragheads?\b",
        r"\btowelheads?\b",
        r"\bchamars?\b",
        r"\bbhangis?\b",
        r"印度阿三",
        r"阿三",
        r"印度佬",
        r"支那",
    )
)

# Generalizations and group blame. These are the lines that get a video
# pulled: "Indians as soon as they see a plane", "as India would tell it,
# the sneaky plane", wishing a crash would "murder a few cows", or blaming
# a faith for the smog.
_GROUP_RES = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bindians?\b.{0,60}\b(?:always|never|whenever|as soon as|are all|are so|are just|can(?:no)?t)\b",
        r"\b(?:all|every|those) indians\b",
        r"\bas india would\b",
        r"\bclever and sneaky\b",
        r"\b(?:deamon|demon|monster|ghost|妖怪).{0,40}\b(?:plane|airplane|aircraft|air-plane)\b",
        r"\b(?:plane|airplane|aircraft|air-plane).{0,48}\b(?:deamon|demon|monster|ghost|妖怪)\b",
        r"印度人(?:一|就|总是|全都|看到|都)",
        r"以为是(?:妖怪|鬼|怪物)",
        r"\b(?:murder|killing|kill)\s+(?:a few\s+|some\s+)?cows?\b",
        r"\bjihadis?\b",
        r"जिहाद",
        r"\bhalala+\b",
        r"हलाला",
        r"mu[s5$]l[i1!]ms?.{0,48}(?:population|wazah|wajah|vajah|pollut)",
        r"(?:population|wazah|wajah).{0,48}mu[s5$]l[i1!]m",
        r"(?:ईद|बकरीद|bakri(?:d| eid)|bakra eid).{0,60}(?:खून|blood|प्रदूष|pollut)",
        r"इस्लामिक प्रदेश",
        r"मुसलमान.{0,24}(?:वजह|प्रदूष)",
        r"मुस्लिम.{0,24}(?:वजह|प्रदूष)",
        r"\b(?:muslims|hindus|sikhs|christians|pakistanis|chinese people)\s+are\s+(?:all\s+)?(?:dirty|stupid|backward|sneaky|liars|terrorists)\b",
    )
)


def _flat(text: str) -> str:
    return (text or "").replace("’", "'").replace("‘", "'")


def reply_excluded(text: str) -> bool:
    """True when this reply must not be drawn or published on the site."""
    flat = _flat(text)
    if not flat.strip():
        return False
    for pattern in _SLUR_RES:
        if pattern.search(flat):
            return True
    for pattern in _GROUP_RES:
        if pattern.search(flat):
            return True
    return False


def filter_replies(replies: list[dict] | None) -> tuple[list[dict], int]:
    """Return (kept replies, number removed). Does not mutate the input list."""
    kept: list[dict] = []
    removed = 0
    for reply in replies or []:
        if not isinstance(reply, dict):
            removed += 1
            continue
        if reply_excluded(str(reply.get("text") or "")):
            removed += 1
            continue
        kept.append(reply)
    return kept, removed
