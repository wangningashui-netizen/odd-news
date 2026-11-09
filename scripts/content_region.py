"""Classify a story's region from its text, not from who published it.

An Indian site republishing a foreign event should not be tagged 印度.
If the title and summary contain no place, currency, or institution signal,
the publisher's region is kept.
"""

from __future__ import annotations

import re

# Longer phrases first so "tamil nadu" wins over a stray "india" only when both exist;
# scoring is additive, so both can count.
INDIA_PHRASES = (
    "tamil nadu", "uttar pradesh", "west bengal", "madhya pradesh", "andhra pradesh",
    "himachal pradesh", "arunachal pradesh", "jammu and kashmir", "dhanushkodi",
    "thiruvananthapuram", "bhubaneswar", "visakhapatnam", "gandhinagar",
    "bengaluru", "bangalore", "hyderabad", "chennai", "kolkata", "mumbai", "delhi",
    "new delhi", "noida", "gurugram", "gurgaon", "ahmedabad", "surat", "jaipur",
    "lucknow", "kanpur", "varanasi", "patna", "indore", "bhopal", "nagpur", "pune",
    "kochi", "goa", "udaipur", "chandigarh", "amritsar", "ludhiana", "karnataka",
    "kerala", "gujarat", "rajasthan", "maharashtra", "telangana", "punjab",
    "haryana", "bihar", "odisha", "orissa", "assam", "jharkhand", "uttarakhand",
    "chhattisgarh", "iitian", "iitians", "iit ", " iit", "iim ", "isro", "rbi",
    "bjp", "rahul gandhi", "narendra modi", "pani puri", "rupee", "rupees",
    "lakh", "crore", "diwali", "deepavali", "hindi",
)
INDIA_WORDS = {"india", "indian", "indians", "₹"}

FOREIGN = (
    ("美国", ("united states", "u.s.", "u.s.a", "white house", "california", "texas", "florida", "new york city", "seattle", "washington d.c")),
    ("英国", ("united kingdom", "britain", "british", "london", "scotland", "manchester", "england")),
    ("日本", ("japan", "japanese", "tokyo", "osaka", "kyoto")),
    ("德国", ("germany", "german", "berlin", "munich")),
    ("中国", ("china", "chinese", "beijing", "shanghai", "shenzhen")),
    ("阿联酋", ("dubai", "abu dhabi", "united arab emirates")),
    ("法国", ("france", "french", "paris")),
    ("澳大利亚", ("australia", "australian", "sydney", "melbourne")),
    ("加拿大", ("canada", "canadian", "toronto", "vancouver")),
    ("韩国", ("south korea", "korean", "seoul")),
)

WORD_RE = re.compile(r"[a-z0-9.]+|₹", re.I)


def _text(title: str, summary: str) -> str:
    return f" {title or ''} {summary or ''} ".lower().replace("₹", " ₹ ")


def _phrase_hit(phrase: str, text: str) -> bool:
    """Multi-word places match as text. Single tokens use a word boundary.

    "rbi" must not match "disturbing" or "barbie", and "goa" must not match "goal".
    """
    if " " in phrase:
        return phrase in text
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def india_score(text: str) -> int:
    score = 0
    if re.search(r"\brs\.?\s*\d", text) or re.search(r"₹\s*\d", text):
        score += 3
    if re.search(r"\b(lakh|crore|lpa)\b", text):
        score += 2
    for phrase in INDIA_PHRASES:
        if _phrase_hit(phrase, text):
            score += 2
    words = set(WORD_RE.findall(text))
    if words & {"india", "indian", "indians"}:
        score += 2
    return score


def foreign_scores(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for region, phrases in FOREIGN:
        hits = sum(1 for phrase in phrases if phrase in text)
        if hits:
            found[region] = hits
    # Bare "us" / "uk" are too noisy; require a word boundary on longer forms already listed.
    if re.search(r"\busa\b|\bu\.s\.\b", text):
        found["美国"] = found.get("美国", 0) + 1
    if re.search(r"\buk\b", text) and "ukraine" not in text:
        found["英国"] = found.get("英国", 0) + 1
    return found


def classify_region(title: str, summary: str, source_region: str) -> str:
    text = _text(title, summary)
    india = india_score(text)
    foreign = foreign_scores(text)
    top_foreign = max(foreign.values()) if foreign else 0
    foreign_region = max(foreign, key=foreign.get) if foreign else ""
    if india and india >= top_foreign:
        return "印度"
    if top_foreign and top_foreign > india:
        if len(foreign) > 1 and top_foreign == 1:
            return "全球"
        return foreign_region
    return source_region or "全球"
