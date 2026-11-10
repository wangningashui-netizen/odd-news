"""Classify a story's region from its text, not from who published it.

An Indian site republishing a foreign event should not be tagged 印度.
A named foreign country, leader, or institution outweighs the publisher.
If the title and summary contain no place, currency, or institution signal,
the publisher's region is kept. An India signal at least as strong as the
strongest foreign signal stays 印度, so a Modi or Delhi story that also
mentions Trump is still India.
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
    "bjp", "rahul gandhi", "narendra modi", "modi", "pani puri", "rupee", "rupees",
    "lakh", "crore", "diwali", "deepavali", "hindi", "hindus", "hindu", "hindustan",
    "dalit", "kohli", "cv raman", "c.v. raman", "tata",
)
INDIA_WORDS = {"india", "indian", "indians", "₹"}

FOREIGN = (
    ("美国", (
        "united states", "u.s.", "u.s.a", "white house", "oval office", "pentagon",
        "mar-a-lago", "california", "texas", "florida", "new york city", "seattle",
        "washington d.c", "los angeles", "nashville",
        "trump", "hegseth", "pete hegseth", "war secretary",
    )),
    ("英国", ("united kingdom", "britain", "british", "london", "scotland", "manchester", "england")),
    ("日本", ("japan", "japanese", "tokyo", "osaka", "kyoto")),
    ("德国", ("germany", "german", "berlin", "munich")),
    ("中国", ("china", "chinese", "beijing", "shanghai", "shenzhen")),
    ("阿联酋", ("dubai", "abu dhabi", "united arab emirates")),
    ("法国", ("france", "french", "paris")),
    ("澳大利亚", ("australia", "australian", "sydney", "melbourne")),
    ("加拿大", ("canada", "canadian", "toronto", "vancouver")),
    ("韩国", ("south korea", "korean", "seoul")),
    ("巴拉圭", ("paraguay", "paraguayan", "asuncion", "asunción")),
    ("伊朗", ("iran", "iranian", "tehran")),
    ("以色列", ("israel", "israeli", "netanyahu", "tel aviv")),
    ("乌克兰", ("ukraine", "ukrainian", "zelensky", "zelenskyy", "kyiv", "kiev")),
    ("俄罗斯", ("russia", "russian", "moscow", "putin")),
    ("卡塔尔", ("qatar", "qatari", "doha")),
    ("委内瑞拉", ("venezuela", "venezuelan", "maduro")),
    ("沙特", ("saudi arabia", "saudi", "riyadh")),
    ("巴西", ("brazil", "brazilian", "brasilia")),
    ("墨西哥", ("mexico", "mexican")),
    ("巴基斯坦", ("pakistan", "pakistani", "islamabad")),
    ("孟加拉", ("bangladesh", "bangladeshi", "dhaka")),
    ("尼泊尔", ("nepal", "nepalese", "kathmandu")),
    ("斯里兰卡", ("sri lanka", "colombo")),
    ("阿富汗", ("afghanistan", "kabul")),
    ("伊拉克", ("iraq", "iraqi", "baghdad")),
    ("叙利亚", ("syria", "syrian", "damascus")),
    ("土耳其", ("türkiye", "turkish", "ankara", "erdogan")),
    ("埃及", ("egypt", "egyptian", "cairo")),
    ("南非", ("south africa", "johannesburg")),
    ("尼日利亚", ("nigeria", "nigerian", "lagos")),
    ("印度尼西亚", ("indonesia", "indonesian", "jakarta")),
    ("菲律宾", ("philippines", "filipino", "manila")),
    ("越南", ("vietnam", "vietnamese", "hanoi")),
    ("泰国", ("thailand", "bangkok")),
    ("马来西亚", ("malaysia", "malaysian", "kuala lumpur")),
    ("缅甸", ("myanmar", "burma")),
    ("新加坡", ("singapore", "singaporean")),
    ("阿根廷", ("argentina", "buenos aires")),
    ("哥伦比亚", ("colombia", "colombian")),
    ("古巴", ("cuba", "cuban", "havana")),
    ("朝鲜", ("pyongyang", "north korea")),
    ("新西兰", ("new zealand",)),
    ("爱尔兰", ("ireland", "irish", "dublin")),
    ("意大利", ("italy", "italian", "rome")),
    ("西班牙", ("spain", "madrid")),
    ("荷兰", ("netherlands", "amsterdam", "dutch")),
    ("瑞典", ("sweden", "swedish", "stockholm")),
    ("挪威", ("norway", "norwegian", "oslo")),
    ("瑞士", ("switzerland", "swiss", "geneva")),
    ("比利时", ("belgium", "brussels")),
    ("波兰", ("poland", "warsaw")),
    ("希腊", ("greece", "athens")),
    ("葡萄牙", ("portugal", "lisbon")),
    ("奥地利", ("austria", "vienna")),
    ("丹麦", ("denmark", "copenhagen")),
    ("芬兰", ("finland", "finnish", "helsinki")),
    ("欧洲", ("european parliament", "european union")),
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
        hits = sum(1 for phrase in phrases if _phrase_hit(phrase, text))
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
