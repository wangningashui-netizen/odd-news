"""Group stories about the same event across sources and a few days.

Deterministic: no network and no paid API. Each item is compared only with
items published within three days. Two items merge when their English titles
and summaries share enough content words, character 3-grams, or a distinctive
token plus a number. Generic words (india, viral, police, diwali) do not
merge stories by themselves.

cluster_id is the id of the earliest item in the group, so it stays put as
long as that item remains.
"""

from __future__ import annotations

import re
from datetime import datetime

WINDOW_DAYS = 3
# Tuned on the Nov 2026 corpus: E20/ethanol stories join; the 45 LPA job
# story does not join the 37 LPA resignation; separate Diwali bonus videos
# stay apart unless they share the Surat businessman details.
TITLE_JACCARD_MIN = 0.42
NGRAM_JACCARD_MIN = 0.38
LOOSE_JACCARD_MIN = 0.22
MIN_SHARED_WORDS = 2

# Words that show up in many unrelated posts. They never count as evidence.
WEAK = {
    "happy", "diwali", "deepavali", "rangoli", "everyone", "festival", "puja",
    "muhurat", "bonus", "employee", "employees", "staff", "gift", "gifts",
    "goes", "going", "internet", "watch", "video", "viral", "says", "said",
    "india", "indian", "karnataka",
}

STOP = {
    "the", "and", "for", "with", "from", "that", "this", "was", "were", "are",
    "been", "being", "have", "has", "had", "his", "her", "their", "they", "them",
    "she", "him", "who", "what", "when", "where", "which", "while", "into", "over",
    "after", "before", "about", "amid", "among", "between", "under", "than", "then",
    "also", "just", "only", "more", "most", "some", "such", "other", "into", "onto",
    "says", "said", "say", "claim", "claims", "claimed", "alleged", "allegedly",
    "report", "reports", "reported", "according", "source", "sources", "news",
    "video", "viral", "internet", "online", "social", "media", "users", "user",
    "people", "person", "man", "woman", "men", "women", "year", "years", "day",
    "days", "new", "old", "first", "last", "one", "two", "three", "its", "it's",
    "not", "but", "you", "your", "our", "out", "off", "how", "why", "can", "may",
    "will", "would", "could", "should", "india", "indian", "indians", "govt",
    "government", "minister", "official", "officials", "police", "court", "state",
    "city", "district", "districts", "centre", "center", "central", "union",
    "watch", "read", "latest", "update", "updates", "breaking", "exclusive",
    "here", "what", "happened", "heres", "here's", "via", "http", "https", "www",
    "com", "html", "article", "story", "times", "now", "ndtv", "news18",
    "link", "links", "comments", "comment",
}

TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?|₹|rs", re.I)
URL_RE = re.compile(r"https?://\S+")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def _parse_day(value: str) -> datetime | None:
    if not value or len(value) < 10:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def content_tokens(text: str) -> list[str]:
    cleaned = URL_RE.sub(" ", text or "")
    cleaned = cleaned.replace("₹", " rs ")
    words = [w.lower() for w in TOKEN_RE.findall(cleaned)]
    return [w for w in words if w not in STOP and w not in WEAK and len(w) > 2 and not w.isdigit()]


def title_tokens(text: str) -> set[str]:
    return {token for token in content_tokens(text) if token not in WEAK}


def numbers(text: str) -> set[str]:
    found = set()
    for raw in NUMBER_RE.findall(text or ""):
        bare = raw.rstrip("%")
        if bare in {"1", "2", "3", "4", "5"}:
            continue
        found.add(raw.lower())
        whole = bare.split(".", 1)[0]
        if whole.isdigit() and int(whole) >= 10:
            found.add(whole)
    return found


def _ethanol_story(text: str) -> bool:
    lowered = (text or "").lower()
    return "ethanol" in lowered or bool(re.search(r"\be[23]0\b", lowered))


def ngrams(text: str, size: int = 3) -> set[str]:
    compact = re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    if len(compact) < size:
        return set()
    return {compact[i : i + size] for i in range(len(compact) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def same_event(left: dict, right: dict) -> bool:
    left_text = f"{left.get('title_en') or ''} {left.get('summary_en') or ''}"
    right_text = f"{right.get('title_en') or ''} {right.get('summary_en') or ''}"
    if _ethanol_story(left_text) and _ethanol_story(right_text):
        # "e20" and "ethanol" are the same fuel story only when the headlines
        # also share a concrete word such as petrol. Two headlines that both
        # say ethanol still join on that shared token.
        family = {"ethanol", "e20", "e30"}
        left_words = set(content_tokens(left_text))
        right_words = set(content_tokens(right_text))
        shared = left_words & right_words
        extra = {word for word in shared - family if len(word) >= 5}
        if shared & family or ((left_words & family) and (right_words & family) and extra):
            return True
    title_left = title_tokens(left.get("title_en") or "")
    title_right = title_tokens(right.get("title_en") or "")
    shared = title_left & title_right
    if len(shared) < MIN_SHARED_WORDS and not (numbers(left.get("title_en")) & numbers(right.get("title_en"))):
        body_left = set(content_tokens(f"{left.get('title_en') or ''} {left.get('summary_en') or ''}"))
        body_right = set(content_tokens(f"{right.get('title_en') or ''} {right.get('summary_en') or ''}"))
        shared = body_left & body_right
        title_left, title_right = body_left, body_right
    if len(shared) < MIN_SHARED_WORDS:
        return False
    jacc = _jaccard(title_left, title_right)
    gram = _jaccard(ngrams(left.get("title_en") or ""), ngrams(right.get("title_en") or ""))
    shared_numbers = numbers(f"{left.get('title_en')} {left.get('summary_en')}") & numbers(
        f"{right.get('title_en')} {right.get('summary_en')}"
    )
    distinctive = {word for word in shared if len(word) >= 6}
    if jacc >= TITLE_JACCARD_MIN and len(shared) >= 3:
        return True
    if gram >= NGRAM_JACCARD_MIN and len(shared) >= MIN_SHARED_WORDS:
        return True
    if shared_numbers and distinctive and jacc >= LOOSE_JACCARD_MIN and len(shared) >= MIN_SHARED_WORDS:
        return True
    if len(distinctive) >= 3 and jacc >= LOOSE_JACCARD_MIN:
        return True
    return False


def _span_ok(group: list[dict], item: dict) -> bool:
    days = [_parse_day(member.get("published_at") or "") for member in group]
    item_day = _parse_day(item.get("published_at") or "")
    known = [day for day in days if day] 
    if item_day:
        known.append(item_day)
    if len(known) < 2:
        return True
    return (max(known) - min(known)).days <= WINDOW_DAYS


def cluster_items(items: list[dict]) -> list[list[dict]]:
    """Assign cluster_id, cluster_item_count, and cluster_source_count. Returns groups."""
    ordered = sorted(items, key=lambda item: (item.get("published_at") or "", item.get("id") or ""))
    groups: list[list[dict]] = []
    for item in ordered:
        placed = False
        item_day = _parse_day(item.get("published_at") or "")
        for group in groups:
            newest = _parse_day(group[-1].get("published_at") or "")
            if item_day and newest and (item_day - newest).days > WINDOW_DAYS:
                continue
            if not _span_ok(group, item):
                continue
            if all(same_event(item, member) for member in group):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    clusters: list[list[dict]] = []
    for group in groups:
        group.sort(key=lambda item: (item.get("published_at") or "", item.get("id") or ""))
        cluster_id = group[0].get("id") or ""
        sources = {item.get("source") for item in group if item.get("source")}
        for item in group:
            item["cluster_id"] = cluster_id
            item["cluster_item_count"] = len(group)
            item["cluster_source_count"] = len(sources)
        clusters.append(group)
    return clusters
