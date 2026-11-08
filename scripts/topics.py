"""Transparent keyword tags for short-video topic hunting.

Rules run on the English title and excerpt. A phrase hit is enough to assign
that tag. Up to three tags, highest score first. If nothing matches, 其他.

An optional model pass can replace these tags when MODELS_API_URL or
MODELS_API_KEY is set. The fixed names below are the only allowed labels.
"""

from __future__ import annotations

import re

TAG_ORDER = [
    "街头食物",
    "卫生环境",
    "交通火车",
    "航空出行",
    "诈骗骗局",
    "影视神剧",
    "婚俗宗教",
    "商业套路",
    "科技发明",
    "军事政治",
    "动物",
    "犯罪法律",
    "奇人奇事",
    "科学发现",
    "历史考古",
    "健康医疗",
    "其他",
]

# (phrase, weight). Weight 2 means one hit is enough. Short words use a
# word boundary so "train" does not match "training".
RULES: list[tuple[str, list[tuple[str, int]]]] = [
    (
        "街头食物",
        [
            ("street food", 3),
            ("food stall", 3),
            ("street vendor", 3),
            ("food poison", 3),
            ("food safety", 2),
            ("adulterat", 3),
            ("pani puri", 3),
            ("golgappa", 3),
            ("vada pav", 3),
            ("chaat", 3),
            ("samosa", 2),
            ("biryani", 2),
            ("dhaba", 3),
            ("hawker", 2),
            ("restaurant", 2),
            ("kitchen", 1),
            ("cooking", 1),
            ("recipe", 1),
            ("fssai", 3),
            ("cockroach", 2),
            ("lizard in", 3),
            ("rat in", 2),
            ("gutter oil", 3),
            ("milk ", 1),
        ],
    ),
    (
        "卫生环境",
        [
            ("open defecation", 3),
            ("sanitation", 3),
            ("sewage", 3),
            ("garbage", 2),
            ("rubbish", 2),
            ("landfill", 2),
            ("toilet", 2),
            ("latrine", 3),
            ("drainage", 2),
            ("gutter", 2),
            ("pollut", 2),
            ("unhygienic", 3),
            ("hygiene", 2),
            ("filth", 3),
            ("stench", 2),
            ("manual scaveng", 3),
            ("waste dump", 3),
            ("dirty water", 3),
            ("open sewer", 3),
            ("public urinal", 3),
        ],
    ),
    (
        "交通火车",
        [
            ("train", 2),
            ("railway", 3),
            ("railroad", 3),
            ("indian railways", 3),
            ("mumbai local", 3),
            ("metro", 2),
            ("platform", 1),
            ("rickshaw", 3),
            ("traffic", 2),
            ("pothole", 3),
            ("bus ", 1),
            ("commute", 2),
            ("overcrowd", 2),
            ("level crossing", 3),
            ("highway", 1),
            ("road accident", 3),
            ("collision", 1),
            ("scooter", 2),
            ("bike taxi", 2),
        ],
    ),
    (
        "航空出行",
        [
            ("airline", 3),
            ("airport", 3),
            ("aviation", 3),
            ("flight", 2),
            ("pilot", 2),
            ("aircraft", 3),
            ("airplane", 3),
            ("aeroplane", 3),
            ("plane", 2),
            ("runway", 3),
            ("boarding", 2),
            ("air india", 3),
            ("indigo", 2),
            ("spicejet", 3),
            ("cabin crew", 3),
            ("helicopter", 2),
            ("dgca", 3),
        ],
    ),
    (
        "诈骗骗局",
        [
            ("scam", 3),
            ("fraud", 3),
            ("swindle", 3),
            ("conman", 3),
            ("con man", 3),
            ("phishing", 3),
            ("tech support", 3),
            ("call centre", 3),
            ("call center", 3),
            ("otp", 2),
            ("ponzi", 3),
            ("chit fund", 3),
            ("fake call", 3),
            ("impersonat", 2),
            ("digital arrest", 3),
            ("sim swap", 3),
            ("cyber crime", 2),
            ("cybercrime", 2),
            ("cheated", 2),
            ("duped", 3),
            ("fake job", 3),
        ],
    ),
    (
        "影视神剧",
        [
            ("bollywood", 3),
            ("tollywood", 3),
            ("kollywood", 3),
            ("film", 1),
            ("movie", 2),
            ("cinema", 2),
            ("actor", 1),
            ("actress", 2),
            ("stunt", 2),
            ("action scene", 3),
            ("soap opera", 3),
            ("tv serial", 3),
            ("web series", 2),
            ("box office", 2),
            ("item song", 3),
            ("trailer", 1),
        ],
    ),
    (
        "婚俗宗教",
        [
            ("wedding", 3),
            ("marriage", 2),
            ("dowry", 3),
            ("baraat", 3),
            ("bride", 2),
            ("groom", 2),
            ("ritual", 2),
            ("temple", 2),
            ("mosque", 2),
            ("church", 1),
            ("festival", 2),
            ("diwali", 2),
            ("dipawali", 2),
            ("deepavali", 2),
            ("holi", 2),
            ("puja", 3),
            ("pujo", 3),
            ("rangoli", 3),
            ("mehendi", 3),
            ("mehndi", 3),
            ("garba", 3),
            ("navratri", 2),
            ("caste", 2),
            ("custom", 1),
            ("ceremony", 2),
            ("procession", 1),
        ],
    ),
    (
        "商业套路",
        [
            ("startup", 2),
            ("jugaad", 3),
            ("pyramid scheme", 3),
            ("mlm", 3),
            ("overcharg", 3),
            ("shopkeeper", 2),
            ("tax evasion", 3),
            ("shell company", 3),
            ("stock tip", 2),
            ("ipo", 1),
            ("billionaire", 2),
            ("businessman", 2),
            ("company", 1),
            ("corporate", 1),
            ("investor", 1),
            ("bonus", 1),
        ],
    ),
    (
        "科技发明",
        [
            ("invent", 3),
            ("innovat", 2),
            ("patent", 2),
            ("isro", 3),
            ("satellite", 2),
            ("robot", 2),
            ("artificial intelligence", 2),
            ("gadget", 2),
            ("prototype", 2),
            ("app ", 1),
            ("scientist", 1),
            ("engineer", 1),
            ("drone", 2),
            ("made in india", 2),
        ],
    ),
    (
        "军事政治",
        [
            ("army", 2),
            ("military", 3),
            ("missile", 3),
            ("navy", 2),
            ("air force", 3),
            ("soldier", 2),
            ("border", 1),
            ("election", 2),
            ("minister", 2),
            ("parliament", 2),
            ("modi", 2),
            ("politician", 2),
            ("government", 1),
            ("superpower", 3),
            ("nuclear", 2),
            ("defence", 2),
            ("defense", 2),
            ("boast", 2),
            ("war ", 1),
        ],
    ),
    (
        "动物",
        [
            ("animal", 2),
            ("dog", 2),
            ("cow", 2),
            ("bull", 2),
            ("snake", 2),
            ("elephant", 2),
            ("monkey", 2),
            ("tiger", 2),
            ("leopard", 2),
            ("crocodile", 2),
            ("stray", 2),
            ("wildlife", 2),
            ("bird", 1),
            ("pet ", 1),
            ("bear", 2),
        ],
    ),
    (
        "犯罪法律",
        [
            ("murder", 3),
            ("killed", 2),
            ("arrest", 2),
            ("police", 2),
            ("court", 1),
            ("jail", 2),
            ("prison", 2),
            ("theft", 2),
            ("robbery", 3),
            ("rape", 3),
            ("crime", 2),
            ("smuggl", 2),
            ("accused", 2),
            ("verdict", 2),
            ("fir ", 2),
            ("gang", 1),
            ("illegal", 1),
        ],
    ),
    (
        "奇人奇事",
        [
            ("guinness", 3),
            ("world record", 3),
            ("eccentric", 3),
            ("bizarre", 2),
            ("oddity", 3),
            ("viral video", 2),
            ("went viral", 2),
            ("goes viral", 2),
            ("stunt", 1),
        ],
    ),
    (
        "科学发现",
        [
            ("study finds", 3),
            ("scientists", 2),
            ("researchers", 2),
            ("discovery", 2),
            ("experiment", 2),
            ("fossil", 2),
            ("species", 2),
            ("nasa", 2),
            ("telescope", 2),
            ("physics", 2),
        ],
    ),
    (
        "历史考古",
        [
            ("archaeolog", 3),
            ("ancient", 2),
            ("excavation", 3),
            ("ruins", 2),
            ("century-old", 2),
            ("historic", 1),
            ("museum", 1),
            ("artefact", 3),
            ("artifact", 2),
            ("dynasty", 2),
        ],
    ),
    (
        "健康医疗",
        [
            ("hospital", 2),
            ("doctor", 2),
            ("medical", 2),
            ("disease", 2),
            ("virus", 1),
            ("surgery", 2),
            ("patient", 1),
            ("cancer", 2),
            ("vaccine", 2),
            ("clinic", 2),
            ("health", 1),
        ],
    ),
]

_WORD = re.compile(r"^[a-z0-9]+$")


def _hit(text: str, phrase: str) -> bool:
    if _WORD.match(phrase) and len(phrase) <= 12:
        return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None
    return phrase in text


def classify_text(title: str, summary: str) -> list[str]:
    text = f"{title or ''}\n{summary or ''}".lower()
    scored: list[tuple[int, int, str]] = []
    for index, (tag, phrases) in enumerate(RULES):
        score = 0
        for phrase, weight in phrases:
            if _hit(text, phrase):
                score += weight
        if score:
            scored.append((score, index, tag))
    scored.sort(key=lambda row: (-row[0], row[1]))
    strong = [tag for score, _index, tag in scored if score >= 2][:3]
    if strong:
        return strong
    if scored:
        return [scored[0][2]]
    return ["其他"]


def classify_item(item: dict) -> list[str]:
    return classify_text(item.get("title_en") or "", item.get("summary_en") or "")
