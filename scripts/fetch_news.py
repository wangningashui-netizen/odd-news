#!/usr/bin/env python3
"""Fetch odd-news feeds, dedupe by URL, and write one JSON file per day.

Chinese titles and summaries are generated with GitHub Models when that API
answers. If it does not (retired, rate-limited, or no token), items are still
saved. A machine-translation fallback fills title_zh / summary_zh and marks
translation_status as "fallback" so a later run can replace them with a model
summary. Items that stay untranslated are "pending" and are retried for a week.

Stdlib only. No article images are downloaded into the repo; only URLs.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html as html_lib
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from cluster_items import cluster_items
from content_region import classify_region
from topics import TAG_ORDER, classify_item

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SHANGHAI = timezone(timedelta(hours=8))
TODAY = datetime.now(SHANGHAI).date()

UA = "odd-news-daily/1.0 (+https://github.com/wangningashui-netizen/odd-news)"
# Reddit requires a unique, descriptive User-Agent. Do not use a library default.
REDDIT_UA = "linux:odd-news-daily:1.0.0 (by /u/odd-news-daily)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# News18 answers 403 to the Chrome UA above and 200 to this one. Article pages
# are tried with both.
ARTICLE_UAS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    BROWSER_UA,
)

MODELS_URL = os.environ.get(
    "MODELS_API_URL", "https://models.github.ai/inference/chat/completions"
)
MODELS_MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini")
RETRY_DAYS = 7
META_LIMIT = 1500
TRANSLATE_SEP = "<|/>"
MEGATHREAD_RE = re.compile(
    r"megathread|weekly discussion|discussion thread|free talk|daily discussion|"
    r"random discussion|political discussion|what(?:'|’)s happening",
    re.I,
)
_REDDIT_GATE = threading.Lock()
_REDDIT_NEXT = 0.0

# Feeds verified on 2026-11-08. Dead or empty feeds are documented in README
# and are intentionally not listed here.
SOURCES = [
    {
        "id": "oddity-central",
        "name": "Oddity Central",
        "region": "全球",
        "url": "https://www.odditycentral.com/feed",
        "kind": "rss",
    },
    {
        "id": "all-thats-interesting",
        "name": "All That's Interesting",
        "region": "全球",
        "url": "https://allthatsinteresting.com/feed",
        "kind": "rss",
    },
    {
        "id": "oddee",
        "name": "Oddee",
        "region": "全球",
        "url": "https://www.oddee.com/feed/",
        "kind": "rss",
    },
    {
        "id": "upi-odd",
        "name": "UPI Odd News",
        "region": "美国",
        "url": "https://rss.upi.com/news/odd_news.rss",
        "kind": "rss",
    },
    {
        "id": "atlas-obscura",
        "name": "Atlas Obscura",
        "region": "全球",
        "url": "https://www.atlasobscura.com/feeds/latest",
        "kind": "rss",
    },
    {
        "id": "mirror-weird",
        "name": "Mirror Weird News",
        "region": "英国",
        "url": "https://www.mirror.co.uk/news/weird-news/?service=rss",
        "kind": "rss",
    },
    {
        "id": "daily-star-weird",
        "name": "Daily Star Weird News",
        "region": "英国",
        "url": "https://www.dailystar.co.uk/news/weird-news/?service=rss",
        "kind": "rss",
    },
    {
        "id": "irish-mirror-weird",
        "name": "Irish Mirror Weird News",
        "region": "爱尔兰",
        "url": "https://www.irishmirror.ie/news/weird-news/?service=rss",
        "kind": "rss",
    },
    {
        "id": "metro-weird",
        "name": "Metro Weird",
        "region": "英国",
        "url": "https://metro.co.uk/news/weird/feed/",
        "kind": "rss",
    },
    {
        "id": "express-weird",
        "name": "Express Weird News",
        "region": "英国",
        "url": "https://www.express.co.uk/news/weird?service=rss",
        "kind": "rss",
    },
    {
        "id": "nypost-weird",
        "name": "New York Post Weird But True",
        "region": "美国",
        "url": "https://nypost.com/weird-but-true/feed/",
        "kind": "rss",
    },
    {
        "id": "ht-trending",
        "name": "Hindustan Times Trending",
        "region": "印度",
        "url": "https://www.hindustantimes.com/feeds/rss/trending/rssfeed.xml",
        "kind": "rss",
    },
    {
        "id": "india-today-trending",
        "name": "India Today Trending",
        "region": "印度",
        "url": "https://www.indiatoday.in/rss/1797650",
        "kind": "rss",
    },
    {
        "id": "toi-viral",
        "name": "Times of India Viral News",
        "region": "印度",
        "url": "https://timesofindia.indiatimes.com/rssfeeds/59016670.cms",
        "kind": "rss",
    },
    {
        "id": "soranews24",
        "name": "SoraNews24",
        "region": "日本",
        "url": "https://soranews24.com/feed/",
        "kind": "rss",
    },
    {
        "id": "neatorama",
        "name": "Neatorama",
        "region": "全球",
        "url": "https://www.neatorama.com/feed/",
        "kind": "rss",
    },
    {
        "id": "ladbible-weird",
        "name": "LADbible Weird",
        "region": "英国",
        "url": "https://www.ladbible.com/weird.rss",
        "kind": "rss",
    },
    {
        "id": "unilad-weird",
        "name": "UNILAD Weird",
        "region": "英国",
        "url": "https://www.unilad.com/weird.rss",
        "kind": "rss",
    },
    {
        # NDTV's own FeedBurner offbeat URL returns HTML, and ndtv.com/rss is blocked.
        # This Google News query is restricted to the offbeat section. Links are
        # resolved to www.ndtv.com before anything is saved.
        "id": "ndtv-offbeat",
        "name": "NDTV Offbeat",
        "region": "印度",
        "url": "https://news.google.com/rss/search?q=site:ndtv.com/offbeat+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
        "kind": "google",
        "title_suffix": " - NDTV",
        "expect_host": "ndtv.com",
    },
    {
        "id": "indian-express-trending",
        "name": "Indian Express Trending",
        "region": "印度",
        "url": "https://indianexpress.com/section/trending/feed/",
        "kind": "rss",
    },
    {
        "id": "news18-viral",
        "name": "News18 Viral",
        "region": "印度",
        "url": "https://news.google.com/rss/search?q=site:news18.com/viral+OR+site:news18.com/buzz+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
        "kind": "google",
        "title_suffixes": [" - News18", " - CNN-News18"],
        "expect_host": "news18.com",
    },
    {
        "id": "timesnow-viral",
        "name": "Times Now Viral",
        "region": "印度",
        "url": "https://news.google.com/rss/search?q=site:timesnownews.com+(viral+OR+bizarre+OR+offbeat)+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
        "kind": "google",
        "title_suffix": " - Times Now",
        "expect_host": "timesnownews.com",
    },
    {
        "id": "republic-viral",
        "name": "Republic World Viral",
        "region": "印度",
        "url": "https://news.google.com/rss/search?q=site:republicworld.com+(viral+OR+buzz+OR+offbeat)+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
        "kind": "google",
        "title_suffixes": [" - Republic World", " - Republic"],
        "expect_host": "republicworld.com",
    },
    {
        "id": "reddit-india",
        "name": "Reddit r/india",
        "region": "印度",
        "url": "https://www.reddit.com/r/india/new/.rss?limit=100",
        "kind": "reddit",
        "include_self": True,
    },
    {
        "id": "reddit-indiaspeaks",
        "name": "Reddit r/IndiaSpeaks",
        "region": "印度",
        "url": "https://www.reddit.com/r/IndiaSpeaks/new/.rss?limit=100",
        "kind": "reddit",
        "include_self": True,
    },
    {
        "id": "reddit-indiasocial",
        "name": "Reddit r/indiasocial",
        "region": "印度",
        "url": "https://www.reddit.com/r/indiasocial/new/.rss?limit=100",
        "kind": "reddit",
        "include_self": True,
    },
    {
        "id": "reddit-nottheonion",
        "name": "Reddit r/nottheonion",
        "region": "全球",
        "url": "https://www.reddit.com/r/nottheonion/new/.rss?limit=100",
        "kind": "reddit",
    },
    {
        "id": "reddit-offbeat",
        "name": "Reddit r/Offbeat",
        "region": "全球",
        "url": "https://www.reddit.com/r/Offbeat/new/.rss?limit=100",
        "kind": "reddit",
    },
]

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "igsh",
    "ref",
    "ref_src",
    "ref_url",
    "cmpid",
    "ncid",
    "soc_src",
    "soc_trk",
    "at_medium",
    "at_campaign",
    "spm",
    "ocid",
    "ito",
    "ns_mchannel",
    "ns_source",
    "ns_campaign",
    "ns_linkname",
}

SSL_CTX = ssl.create_default_context()
TAG_RE = re.compile(r"<[^>]+>")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)
LINK_POST_RE = re.compile(
    r"""href=["'](https?://[^"']+)["'][^>]*>\s*\[link\]\s*</a>""", re.I
)
BOILER_RE = re.compile(
    r"\s*(The post .+ appeared first on .+|Continue reading(?:\s+.+)?|Read more(?:\s+at)?.+)$",
    re.I,
)


def log(msg: str) -> None:
    print(msg, flush=True)


def local_name(tag: str) -> str:
    if not tag:
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("\xa0", " ")
    text = CTRL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def html_to_bits(raw: str) -> tuple[str, str | None]:
    if not raw:
        return "", None
    text = html_lib.unescape(raw)
    if "&lt;" in text or "&#" in text:
        text = html_lib.unescape(text)
    image = None
    match = IMG_SRC_RE.search(text)
    if match:
        image = html_lib.unescape(match.group(1).strip())
    plain = TAG_RE.sub(" ", text)
    plain = html_lib.unescape(plain)
    plain = BOILER_RE.sub("", plain)
    return clean_text(plain), image


def clip_summary(text: str, sentences: int = 4, max_chars: int = 520) -> str:
    text = clean_text(text)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    kept: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        kept.append(part)
        if len(kept) >= sentences:
            break
    clipped = " ".join(kept) if kept else text
    if len(clipped) > max_chars:
        clipped = clipped[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return clipped


def has_cjk(text: str | None) -> bool:
    return bool(text and CJK_RE.search(text))


def parse_datetime(value: str) -> datetime | None:
    value = clean_text(value)
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(SHANGHAI)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    candidate = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SHANGHAI)


def iso_shanghai(dt: datetime) -> str:
    return dt.astimezone(SHANGHAI).isoformat(timespec="seconds")


def dedupe_key(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(":80") and parts.scheme in ("http", "https"):
        host = host[:-3]
    if host.endswith(":443"):
        host = host[:-4]
    path = parts.path.rstrip("/") or "/"
    query_pairs = []
    for key, val in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        query_pairs.append((lowered, val))
    query_pairs.sort()
    query = urllib.parse.urlencode(query_pairs)
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    base = f"{scheme}://{host}{path}"
    return f"{base}?{query}" if query else base


def display_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    query_pairs = []
    for key, val in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        query_pairs.append((key, val))
    query = urllib.parse.urlencode(query_pairs)
    path = parts.path or "/"
    cleaned = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, ""))
    return cleaned


def fetch_url(url: str, ua: str, timeout: int, limit: int) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=SSL_CTX) as response:
        status = getattr(response, "status", 200)
        final = response.geturl()
        ctype = response.headers.get("content-type", "")
        raw = response.read(limit)
        encoding = (response.headers.get("content-encoding") or "").lower()
        if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except gzip.BadGzipFile:
                pass
        charset = "utf-8"
        match = re.search(r"charset=([\w.-]+)", ctype, re.I)
        if match:
            charset = match.group(1)
        try:
            text = raw.decode(charset, "replace")
        except LookupError:
            text = raw.decode("utf-8", "replace")
        return status, final, text


def fetch_feed(source: dict) -> tuple[dict, str | None, str | None]:
    ua = REDDIT_UA if source["kind"] == "reddit" else UA
    if source["kind"] == "reddit":
        global _REDDIT_NEXT
        with _REDDIT_GATE:
            wait = _REDDIT_NEXT - time.time()
            if wait > 0:
                time.sleep(wait)
            _REDDIT_NEXT = time.time() + 1.2
    last_error = None
    for attempt in range(2):
        try:
            status, final, text = fetch_url(source["url"], ua, timeout=25, limit=2_000_000)
            if status != 200:
                last_error = f"HTTP {status}"
                continue
            head = text.lstrip()[:400].lower()
            if "<rss" not in head and "<feed" not in head and "<rdf" not in head and "<?xml" not in head:
                last_error = f"not a feed ({final[:80]})"
                continue
            return source, text, None
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the run
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.8 * (attempt + 1))
    return source, None, last_error


def parse_xml(text: str) -> ET.Element:
    stripped = text.lstrip("\ufeff")
    try:
        return ET.fromstring(stripped)
    except ET.ParseError:
        repaired = re.sub(r"&(?!#?\w+;)", "&amp;", stripped)
        return ET.fromstring(repaired)


def child_map(element: ET.Element) -> dict[str, list[ET.Element]]:
    grouped: dict[str, list[ET.Element]] = {}
    for child in list(element):
        grouped.setdefault(local_name(child.tag), []).append(child)
    return grouped


def element_text(nodes: list[ET.Element] | None) -> str:
    if not nodes:
        return ""
    return clean_text("".join(nodes[0].itertext()))


def pick_image(grouped: dict[str, list[ET.Element]], html_blobs: list[str]) -> str | None:
    candidates: list[tuple[int, int, str]] = []

    def add(url: str | None, priority: int, width: int) -> None:
        if not url:
            return
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return
        lowered = url.lower()
        if any(token in lowered for token in ("1x1", "spacer", "pixel.gif", "blank.gif", "badge")):
            return
        candidates.append((priority, width, url))

    for node in grouped.get("content", []):
        mime = (node.attrib.get("medium") or node.attrib.get("type") or "").lower()
        url = node.attrib.get("url")
        if mime and "image" not in mime and not mime.startswith("image"):
            if url and not re.search(r"\.(jpe?g|png|gif|webp)(\?|$)", url, re.I):
                continue
        width = 0
        try:
            width = int(float(node.attrib.get("width") or 0))
        except ValueError:
            width = 0
        add(url, 3, width)
    for node in grouped.get("enclosure", []):
        mime = (node.attrib.get("type") or "").lower()
        url = node.attrib.get("url")
        if mime and not mime.startswith("image"):
            continue
        length = 0
        try:
            length = int(node.attrib.get("length") or 0)
        except ValueError:
            length = 0
        add(url, 3, min(length // 1000, 5000))
    for node in grouped.get("thumbnail", []):
        add(node.attrib.get("url"), 2, 0)
    for blob in html_blobs:
        _plain, img = html_to_bits(blob)
        add(img, 1, 0)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[-1][2]


def reddit_external_url(html: str) -> str | None:
    if not html:
        return None
    unescaped = html_lib.unescape(html)
    match = LINK_POST_RE.search(unescaped)
    if not match:
        return None
    url = match.group(1)
    host = urllib.parse.urlsplit(url).netloc.lower()
    if host.endswith("reddit.com") or host.endswith("redd.it"):
        return None
    return url


def decode_google_news_url(article_url: str) -> str | None:
    """Turn a news.google.com/rss/articles link into the publisher URL."""
    article_id = urllib.parse.urlsplit(article_url).path.rstrip("/").split("/")[-1]
    article_id = article_id.split("?")[0]
    try:
        # The signature sits at the end of a large HTML shell, so read the whole page.
        _status, _final, html = fetch_url(article_url, BROWSER_UA, timeout=20, limit=1_200_000)
    except Exception:
        return None
    signature = re.search(r'data-n-a-sg="([^"]+)"', html)
    timestamp = re.search(r'data-n-a-ts="([^"]+)"', html)
    if not signature or not timestamp:
        return None
    inner = [
        "garturlreq",
        [
            ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
            "X",
            "X",
            1,
            [1, 1, 1],
            1,
            1,
            None,
            0,
            0,
            None,
            0,
        ],
        article_id,
        int(timestamp.group(1)),
        html_lib.unescape(signature.group(1)),
    ]
    payload = json.dumps([[["Fbv4je", json.dumps(inner, separators=(",", ":")), None, "generic"]]])
    body = urllib.parse.urlencode({"f.req": payload}).encode()
    path = urllib.parse.urlsplit(article_url).path
    post_url = (
        "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je&source-path="
        + urllib.parse.quote(path)
        + "&hl=en-US&rt=c"
    )
    request = urllib.request.Request(
        post_url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": BROWSER_UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20, context=SSL_CTX) as response:
            raw = response.read().decode("utf-8", "replace")
    except Exception:
        return None
    found = re.findall(r"https://[^\"\\]+", raw)
    for url in found:
        if "news.google." in url or "gstatic.com" in url or "googleusercontent" in url:
            continue
        if "/amp/" in url:
            continue
        return url
    return None


def resolve_google_entries(entries: list[dict], source: dict | None = None) -> list[dict]:
    resolved: list[dict] = []
    expect = ((source or {}).get("expect_host") or "").lower()

    def work(item: dict) -> dict | None:
        publisher = decode_google_news_url(item["url"])
        if not publisher or not publisher.startswith("http"):
            return None
        host = urllib.parse.urlsplit(publisher).netloc.lower()
        if expect and expect not in host:
            return None
        updated = dict(item)
        updated["url"] = display_url(publisher)
        updated["id"] = hashlib.sha1(dedupe_key(updated["url"]).encode("utf-8")).hexdigest()[:16]
        return updated

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(work, item) for item in entries]
        for future in as_completed(futures):
            item = future.result()
            if item:
                resolved.append(item)
    return resolved


def parse_feed(source: dict, xml_text: str) -> list[dict]:
    root = parse_xml(xml_text)
    items: list[dict] = []
    now = iso_shanghai(datetime.now(SHANGHAI))
    for entry in root.iter():
        if local_name(entry.tag) not in ("item", "entry"):
            continue
        grouped = child_map(entry)
        title = element_text(grouped.get("title"))
        suffixes = list(source.get("title_suffixes") or [])
        if source.get("title_suffix"):
            suffixes.append(source["title_suffix"])
        for suffix in suffixes:
            if suffix and title.endswith(suffix):
                title = title[: -len(suffix)].strip()
                break
        if not title or title.lower() in {"untitled", "(untitled)"}:
            continue
        if source["kind"] == "reddit" and MEGATHREAD_RE.search(title):
            continue
        html_blobs = []
        for key in ("description", "summary", "encoded", "content"):
            for node in grouped.get(key, []):
                html_blobs.append("".join(node.itertext()))
        link = ""
        for node in grouped.get("link", []):
            href = node.attrib.get("href") or element_text([node])
            rel = (node.attrib.get("rel") or "alternate").lower()
            if href and rel in {"alternate", ""}:
                link = href.strip()
                break
        if not link:
            link = element_text(grouped.get("link"))
        if source["kind"] == "reddit":
            content_html = ""
            for node in grouped.get("content", []) + grouped.get("summary", []):
                content_html += "".join(node.itertext())
            external = reddit_external_url(content_html)
            if external:
                link = external
                html_blobs = []
            elif source.get("include_self") and link.startswith("http"):
                plain, _image = html_to_bits(content_html)
                plain = re.sub(r"submitted by /u/\S+", "", plain, flags=re.I).strip()
                html_blobs = [plain] if plain else []
            else:
                continue
        if not link.startswith(("http://", "https://")):
            continue
        summary = ""
        for blob in html_blobs:
            plain, _img = html_to_bits(blob)
            if len(plain) > len(summary):
                summary = plain
        summary = clip_summary(summary)
        folded_title = re.sub(r"\s+", " ", title).strip().lower()
        folded_summary = re.sub(r"\s+", " ", summary).strip().lower()
        trimmed_summary = re.sub(r"[\s\-–—|:]+[a-z0-9 .']{2,24}$", "", folded_summary).strip()
        if not folded_summary or folded_summary == folded_title or trimmed_summary == folded_title:
            summary = ""
        elif folded_summary.startswith(folded_title) and len(folded_summary) <= len(folded_title) + 16:
            summary = ""
        published = None
        for key in ("pubdate", "published", "updated", "date"):
            raw_date = element_text(grouped.get(key))
            published = parse_datetime(raw_date)
            if published:
                break
        if published is None:
            published = datetime.now(SHANGHAI)
        image = pick_image(grouped, html_blobs if source["kind"] != "reddit" else [])
        if source["kind"] == "reddit":
            for node in grouped.get("thumbnail", []):
                thumb = (node.attrib.get("url") or "").strip()
                if thumb.startswith("http") and "redditstatic.com" not in thumb:
                    image = thumb
                    break
        url = display_url(link)
        items.append(
            {
                "id": hashlib.sha1(dedupe_key(url).encode("utf-8")).hexdigest()[:16],
                "url": url,
                "title_en": clean_text(title)[:300],
                "title_zh": None,
                "summary_en": summary,
                "summary_zh": None,
                "translation_status": "pending",
                "image": image,
                "image_checked": bool(image) and len(summary) >= 80,
                "source": source["name"],
                "source_id": source["id"],
                "region": source["region"],
                "published_at": iso_shanghai(published),
                "fetched_at": now,
            }
        )
        if source["kind"] == "reddit":
            entry_id = element_text(grouped.get("id"))
            if entry_id.startswith("t3_"):
                items[-1]["reddit_id"] = entry_id
    return items


def load_days() -> dict[str, list[dict]]:
    days: dict[str, list[dict]] = {}
    if not DATA.exists():
        return days
    for path in sorted(DATA.glob("????-??-??.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log(f"skip unreadable {path.name}: {exc}")
            continue
        date = payload.get("date") or path.stem
        days[date] = list(payload.get("items") or [])
    return days


def known_keys(days: dict[str, list[dict]]) -> set[str]:
    keys: set[str] = set()
    for items in days.values():
        for item in items:
            url = item.get("url") or ""
            if url:
                keys.add(dedupe_key(url))
    return keys


def thin_summary(item: dict) -> bool:
    """True when there is no real excerpt, only a title restated as the summary."""
    english = (item.get("summary_en") or "").strip()
    chinese = (item.get("summary_zh") or "").strip()
    title_en = (item.get("title_en") or "").strip()
    title_zh = (item.get("title_zh") or "").strip()
    if len(english) < 40 or english.lower() == title_en.lower():
        if not chinese or (title_zh and chinese == title_zh):
            return True
    if chinese and title_zh and chinese == title_zh and len(english) < 40:
        return True
    return False


def needs_meta(item: dict) -> bool:
    if item.get("page_fetched"):
        return False
    if int(item.get("page_attempts") or 0) >= 2:
        return False
    if not item.get("image"):
        return True
    return thin_summary(item)


def extract_meta(html: str, page_url: str) -> tuple[str | None, str | None]:
    def grab(prop: str) -> str | None:
        patterns = [
            rf'<meta[^>]+(?:property|name|itemprop)=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\']{prop}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                return html_lib.unescape(match.group(1).strip())
        return None

    image = grab("og:image") or grab("og:image:url") or grab("twitter:image") or grab("twitter:image:src")
    description = grab("og:description") or grab("description")
    if image:
        image = urllib.parse.urljoin(page_url, html_lib.unescape(image))
        if not image.startswith(("http://", "https://")):
            image = None
    if description:
        description = clip_summary(description)
    if not description or len(description) < 40:
        description = first_paragraph(html) or description
    return image, description


def first_paragraph(html: str) -> str | None:
    for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", html, re.I | re.S):
        text = TAG_RE.sub(" ", match.group(1))
        text = clip_summary(html_lib.unescape(text))
        lowered = text.lower()
        if len(text) < 80:
            continue
        if any(token in lowered for token in ("cookie", "subscribe", "sign up", "advertisement", "newsletter")):
            continue
        return text
    return None


def fetch_article(url: str) -> str | None:
    for agent in ARTICLE_UAS:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=12, context=SSL_CTX) as response:
                raw = response.read(260_000)
                if raw[:2] == b"\x1f\x8b":
                    try:
                        raw = gzip.decompress(raw)
                    except gzip.BadGzipFile:
                        pass
                text = raw.decode("utf-8", "replace")
        except Exception:
            continue
        if "<html" in text.lower() or "<meta" in text.lower():
            return text
    return None


def enrich_one(item: dict) -> dict:
    updated = dict(item)
    if not needs_meta(updated):
        return updated
    html = fetch_article(updated["url"])
    if not html:
        updated["page_attempts"] = int(updated.get("page_attempts") or 0) + 1
        return updated
    image, description = extract_meta(html, updated["url"])
    if image and (not updated.get("image") or "redd.it" in (updated.get("image") or "")):
        updated["image"] = image
    if description and thin_summary(updated) and len(description) > len(updated.get("summary_en") or ""):
        updated["summary_en"] = description
        # Applied translations stay. A later retranslate run puts them back if a
        # fetch ever rewrites the Chinese fields.
        if updated.get("translation_status") != "ai":
            title_zh = (updated.get("title_zh") or "").strip()
            summary_zh = (updated.get("summary_zh") or "").strip()
            if not summary_zh or summary_zh == title_zh:
                updated["summary_zh"] = None
                if updated.get("translation_status") != "ok":
                    updated["translation_status"] = "pending"
    updated["page_fetched"] = True
    updated["image_checked"] = True
    return updated


def enrich_items(items: list[dict]) -> None:
    pending = [item for item in items if needs_meta(item)]
    pending.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    pending.sort(key=lambda item: item.get("region") != "印度")
    pending = pending[:META_LIMIT]
    if not pending:
        return
    log(f"enrich meta for {len(pending)} items")
    by_id = {item["id"]: item for item in items}
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(enrich_one, item) for item in pending]
        for future in as_completed(futures):
            result = future.result()
            by_id[result["id"]].update(result)
            done += 1
            if done % 40 == 0:
                log(f"  enriched {done}/{len(pending)}")
    log(f"  enriched {done}/{len(pending)}")


def recent_items(days: dict[str, list[dict]]) -> list[dict]:
    cutoff = TODAY - timedelta(days=RETRY_DAYS - 1)
    picked: list[dict] = []
    for date, items in days.items():
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < cutoff:
            continue
        picked.extend(items)
    return picked


def models_token() -> str:
    return os.environ.get("MODELS_API_KEY") or os.environ.get("GITHUB_TOKEN") or ""


def post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> tuple[int, str, str]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=SSL_CTX) as response:
            body = response.read(1_000_000).decode("utf-8", "replace")
            ctype = response.headers.get("content-type", "")
            return getattr(response, "status", 200), ctype, body
    except urllib.error.HTTPError as exc:
        body = exc.read(200_000).decode("utf-8", "replace")
        return exc.code, exc.headers.get("content-type", "") if exc.headers else "", body


def probe_models() -> bool:
    token = models_token()
    if not token:
        log("GitHub Models skipped: no token in the environment")
        return False
    status, ctype, body = post_json(
        MODELS_URL,
        {
            "model": MODELS_MODEL,
            "max_tokens": 32,
            "temperature": 0,
            "messages": [
                {"role": "user", "content": "Reply with the single word pong."},
            ],
        },
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=30,
    )
    stripped = body.strip()
    if status == 200 and stripped.startswith("{") and "choices" in stripped:
        log(f"GitHub Models reachable with model {MODELS_MODEL}")
        return True
    log(
        "GitHub Models unavailable "
        f"(HTTP {status}, content-type {ctype or 'unknown'}, body {stripped[:80]!r})"
    )
    return False


def model_translate(batch: list[dict]) -> dict[str, tuple[str, str]]:
    token = models_token()
    payload_items = [
        {
            "id": item["id"],
            "title_en": item.get("title_en") or "",
            "summary_en": item.get("summary_en") or item.get("title_en") or "",
        }
        for item in batch
    ]
    prompt = (
        "你是中文编辑。把下面 JSON 数组里的每条奇闻译成简体中文，供找选题的人快速读懂。\n"
        "只依据给定英文，不要编造原文没有的事实、数字或引语。\n"
        "title_zh 是中文标题。summary_zh 是 2 到 4 句的概要；素材很短时写 2 句，不要注水。\n"
        "只返回 JSON 数组，元素为 {\"id\",\"title_zh\",\"summary_zh\"}，不要 Markdown。\n\n"
        + json.dumps(payload_items, ensure_ascii=False)
    )
    status, _ctype, body = post_json(
        MODELS_URL,
        {
            "model": MODELS_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "You output only JSON."},
                {"role": "user", "content": prompt},
            ],
        },
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    if status == 429:
        raise RuntimeError("rate-limited")
    if status != 200 or not body.strip().startswith("{"):
        raise RuntimeError(f"models HTTP {status}: {body.strip()[:120]}")
    outer = json.loads(body)
    content = outer["choices"][0]["message"]["content"]
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    if isinstance(parsed, dict):
        parsed = parsed.get("items") or parsed.get("results") or []
    found: dict[str, tuple[str, str]] = {}
    for row in parsed:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "")
        title = clean_text(row.get("title_zh") or "")
        summary = clean_text(row.get("summary_zh") or "")
        if item_id and has_cjk(title) and has_cjk(summary):
            found[item_id] = (title[:180], summary[:600])
    return found


def gtranslate_many(texts: list[str]) -> list[str]:
    if not texts:
        return []
    payload = f"\n{TRANSLATE_SEP}\n".join(texts)
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
        + urllib.parse.quote(payload)
    )
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(request, timeout=30, context=SSL_CTX) as response:
        body = response.read().decode("utf-8", "replace")
    data = json.loads(body)
    joined = "".join(part[0] for part in data[0] if part and part[0])
    parts = [part.strip() for part in joined.split(TRANSLATE_SEP)]
    if len(parts) != len(texts):
        raise RuntimeError(f"split {len(parts)} != {len(texts)}")
    return parts


def fallback_translate(items: list[dict]) -> None:
    queue = [item for item in items if item.get("translation_status") == "pending" or not item.get("title_zh")]
    if not queue:
        return
    log(f"fallback translation for {len(queue)} items")
    cursor = 0
    done = 0
    while cursor < len(queue):
        batch: list[dict] = []
        texts: list[str] = []
        size = 0
        while cursor < len(queue) and len(batch) < 8:
            item = queue[cursor]
            title = (item.get("title_en") or "").replace(TRANSLATE_SEP, "")
            summary = (item.get("summary_en") or "").replace(TRANSLATE_SEP, "")
            piece = len(title) + len(summary)
            if batch and size + piece > 2200:
                break
            batch.append(item)
            texts.append(title[:240])
            texts.append((summary or title)[:480])
            size += piece
            cursor += 1
        try:
            translated = gtranslate_many(texts)
        except Exception as exc:  # noqa: BLE001
            log(f"  fallback batch failed ({exc}); trying one by one")
            translated = []
            ok = True
            for text in texts:
                try:
                    translated.extend(gtranslate_many([text]))
                    time.sleep(0.15)
                except Exception as inner:  # noqa: BLE001
                    log(f"  fallback item failed: {inner}")
                    ok = False
                    break
            if not ok:
                continue
        for index, item in enumerate(batch):
            title_zh = clean_text(translated[index * 2])
            summary_zh = clean_text(translated[index * 2 + 1])
            if not has_cjk(title_zh):
                continue
            if not has_cjk(summary_zh):
                summary_zh = title_zh
            item["title_zh"] = title_zh[:180]
            item["summary_zh"] = summary_zh[:600]
            item["translation_status"] = "fallback"
            done += 1
        time.sleep(0.25)
    log(f"  fallback translated {done}")


def apply_existing_cjk(item: dict) -> bool:
    title = item.get("title_en") or ""
    summary = item.get("summary_en") or ""
    if has_cjk(title) and (not summary or has_cjk(summary)):
        item["title_zh"] = title
        item["summary_zh"] = summary or title
        item["translation_status"] = "ok"
        return True
    return False


def translate_items(items: list[dict], use_models: bool, use_fallback: bool) -> None:
    for item in items:
        if item.get("translation_status") in {"ok", "ai"} and item.get("title_zh") and item.get("summary_zh"):
            continue
        apply_existing_cjk(item)

    model_queue = [
        item
        for item in items
        if item.get("translation_status") not in {"ok", "ai"}
    ]
    if use_models and model_queue:
        log(f"GitHub Models translation for {len(model_queue)} items")
        index = 0
        disabled = False
        while index < len(model_queue) and not disabled:
            batch = model_queue[index : index + 8]
            index += 8
            for attempt in range(3):
                try:
                    found = model_translate(batch)
                    for item in batch:
                        pair = found.get(item["id"])
                        if not pair:
                            continue
                        item["title_zh"], item["summary_zh"] = pair
                        item["translation_status"] = "ok"
                    break
                except RuntimeError as exc:
                    if "rate-limited" in str(exc) and attempt < 2:
                        wait = 15 * (attempt + 1)
                        log(f"  models rate limited, sleeping {wait}s")
                        time.sleep(wait)
                        continue
                    log(f"  models batch failed: {exc}")
                    if "HTTP" in str(exc) or "models" in str(exc).lower():
                        disabled = True
                    break
                except Exception as exc:  # noqa: BLE001
                    log(f"  models batch failed: {exc}")
                    disabled = True
                    break
            time.sleep(1.5)
    if use_fallback:
        fallback_translate(
            [
                item
                for item in items
                if item.get("translation_status") not in {"ok", "ai"} and not item.get("title_zh")
            ]
        )
        translate_summaries_only(
            [
                item
                for item in items
                if item.get("title_zh")
                and item.get("summary_en")
                and not item.get("summary_zh")
                and item.get("translation_status") not in {"ok", "ai"}
            ]
        )


def translate_summaries_only(items: list[dict]) -> None:
    """Fill summary_zh for items that already have a Chinese title and a new English excerpt."""
    queue = [item for item in items if (item.get("summary_en") or "").strip() and not item.get("summary_zh")]
    if not queue:
        return
    log(f"translate new excerpts for {len(queue)} items")
    cursor = 0
    done = 0
    while cursor < len(queue):
        batch: list[dict] = []
        texts: list[str] = []
        size = 0
        while cursor < len(queue) and len(batch) < 8:
            item = queue[cursor]
            text = (item.get("summary_en") or "").replace(TRANSLATE_SEP, "")[:480]
            if batch and size + len(text) > 2200:
                break
            batch.append(item)
            texts.append(text)
            size += len(text)
            cursor += 1
        try:
            translated = gtranslate_many(texts)
        except Exception as exc:  # noqa: BLE001
            log(f"  excerpt batch failed ({exc})")
            continue
        for item, summary_zh in zip(batch, translated):
            summary_zh = clean_text(summary_zh)
            if not has_cjk(summary_zh):
                continue
            item["summary_zh"] = summary_zh[:600]
            if item.get("translation_status") == "pending":
                item["translation_status"] = "fallback"
            done += 1
        time.sleep(0.25)
    log(f"  excerpts translated {done}")


def llm_retag(days: dict[str, list[dict]]) -> set[str]:
    """Replace rule tags when an OpenAI-compatible model is explicitly configured."""
    if not (os.environ.get("MODELS_API_KEY") or os.environ.get("MODELS_API_URL")):
        return set()
    if not probe_models():
        log("topic model unavailable, keeping keyword tags")
        return set()
    queue = [
        item
        for items in days.values()
        for item in items
        if item.get("tag_source") != "model"
    ][:160]
    if not queue:
        return set()
    log(f"model topic tags for {len(queue)} items")
    dirty: set[str] = set()
    allowed = ", ".join(TAG_ORDER)
    index = 0
    while index < len(queue):
        batch = queue[index : index + 10]
        index += 10
        payload = [
            {
                "id": item["id"],
                "title": item.get("title_en") or "",
                "summary": (item.get("summary_en") or "")[:400],
            }
            for item in batch
        ]
        prompt = (
            "给每条新闻选 1 到 3 个选题标签，只能使用这些标签："
            + allowed
            + "。只依据标题和摘要，不要编造。只返回 JSON 数组，元素为 "
            '{"id","tags"}，tags 是字符串数组。\n'
            + json.dumps(payload, ensure_ascii=False)
        )
        try:
            status, _ctype, body = post_json(
                MODELS_URL,
                {
                    "model": MODELS_MODEL,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": "You output only JSON."},
                        {"role": "user", "content": prompt},
                    ],
                },
                {
                    "Authorization": f"Bearer {models_token()}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            if status != 200 or not body.strip().startswith("{"):
                log(f"  topic model HTTP {status}")
                break
            content = json.loads(body)["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?\s*", "", content.strip())
            content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            log(f"  topic model failed: {exc}")
            break
        found = {}
        for row in parsed if isinstance(parsed, list) else []:
            if not isinstance(row, dict):
                continue
            tags = [tag for tag in row.get("tags") or [] if tag in TAG_ORDER and tag != "其他"]
            tags = tags[:3] or ["其他"]
            found[str(row.get("id") or "")] = tags
        for item in batch:
            tags = found.get(item["id"])
            if not tags:
                continue
            item["tags"] = tags
            item["tag_source"] = "model"
            dirty.add(day_of(item))
        time.sleep(1.0)
    return dirty


def apply_tags(days: dict[str, list[dict]]) -> set[str]:
    dirty: set[str] = set()
    for date, items in days.items():
        for item in items:
            if item.get("tag_source") == "model" and item.get("tags"):
                continue
            tags = classify_item(item)
            if item.get("tags") != tags or item.get("tag_source") != "rules":
                item["tags"] = tags
                item["tag_source"] = "rules"
                dirty.add(date)
    dirty |= llm_retag(days)
    return dirty


def item_sort_key(item: dict) -> tuple[str, str]:
    return (item.get("published_at") or "", item.get("id") or "")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_outputs(days: dict[str, list[dict]], dirty: set[str]) -> None:
    for date in sorted(dirty):
        items = days.get(date) or []
        items.sort(key=item_sort_key, reverse=True)
        days[date] = items
        write_json(
            DATA / f"{date}.json",
            {"date": date, "timezone": "Asia/Shanghai", "count": len(items), "items": items},
        )
    dates = []
    for date in sorted(days.keys(), reverse=True):
        items = days[date]
        if not items:
            continue
        dates.append({"date": date, "count": len(items), "file": f"data/{date}.json"})
    write_json(
        DATA / "index.json",
        {
            "site": "奇闻日报",
            "timezone": "Asia/Shanghai",
            "updated_at": iso_shanghai(datetime.now(SHANGHAI)),
            "dates": dates,
        },
    )
    write_search(days)


REDDIT_STAT_SUBS = ("india", "IndiaSpeaks", "indiasocial", "nottheonion", "Offbeat")


def _arctic_listing(sub: str) -> dict | None:
    """Used only when Reddit's own JSON listing returns 403 or 429."""
    url = (
        "https://arctic-shift.photon-reddit.com/api/posts/search?subreddit="
        + urllib.parse.quote(sub)
        + "&limit=100&sort=desc"
    )
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=25, context=SSL_CTX) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        log(f"reddit mirror skipped r/{sub}: {exc}")
        return None
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    log(f"reddit stats for r/{sub} from public mirror ({len(rows)} posts)")
    return {"data": rows}


def _reddit_json(url: str) -> dict | None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": REDDIT_UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20, context=SSL_CTX) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        log(f"reddit stats skipped {url.split('?')[0]}: {exc}")
        return None


def refresh_reddit_stats(items: list[dict]) -> int:
    """Best-effort upvote and comment counts. A 403 or 429 leaves items unchanged."""
    by_url: dict[str, tuple[int, int, str]] = {}
    for sub in REDDIT_STAT_SUBS:
        payload = _reddit_json(f"https://www.reddit.com/r/{sub}/new.json?limit=100&raw_json=1")
        time.sleep(1.1)
        if not payload:
            payload = _arctic_listing(sub)
        if not payload:
            continue
        raw = payload.get("data")
        if isinstance(raw, list):
            posts = raw
        elif isinstance(raw, dict):
            posts = [child.get("data") or {} for child in raw.get("children") or []]
        else:
            posts = []
        for post in posts:
            stats = (post.get("score"), post.get("num_comments"), post.get("name") or "")
            if stats[0] is None and stats[1] is None:
                continue
            for raw in (post.get("url"), post.get("permalink")):
                if not raw:
                    continue
                if raw.startswith("/"):
                    raw = "https://www.reddit.com" + raw
                by_url[dedupe_key(raw)] = stats
    known_ids = [item["reddit_id"] for item in items if item.get("reddit_id")]
    for start in range(0, len(known_ids), 80):
        chunk = known_ids[start : start + 80]
        payload = _reddit_json("https://www.reddit.com/by_id/" + ",".join(chunk) + ".json?raw_json=1")
        time.sleep(1.1)
        if not payload:
            continue
        for child in (payload.get("data") or {}).get("children") or []:
            post = child.get("data") or {}
            stats = (post.get("score"), post.get("num_comments"), post.get("name") or "")
            for raw in (post.get("url"), post.get("permalink")):
                if not raw:
                    continue
                if raw.startswith("/"):
                    raw = "https://www.reddit.com" + raw
                by_url[dedupe_key(raw)] = stats
    changed = 0
    for item in items:
        if not str(item.get("source") or "").startswith("Reddit"):
            continue
        hit = by_url.get(dedupe_key(item.get("url") or ""))
        if not hit:
            continue
        score, comments, name = hit
        if item.get("reddit_score") != score or item.get("reddit_comments") != comments or (
            name and item.get("reddit_id") != name
        ):
            item["reddit_score"] = score
            item["reddit_comments"] = comments
            if name:
                item["reddit_id"] = name
            changed += 1
    log(f"reddit stats updated {changed}")
    return changed


def apply_derived(days: dict[str, list[dict]]) -> set[str]:
    """Recompute content regions and story clusters. Reddit stats are best-effort."""
    dirty: set[str] = set()
    flat: list[tuple[str, dict]] = []
    for date, items in days.items():
        for item in items:
            if not item.get("source_region"):
                item["source_region"] = item.get("region") or "全球"
                dirty.add(date)
            new_region = classify_region(
                item.get("title_en") or "",
                item.get("summary_en") or "",
                item.get("source_region") or "全球",
            )
            if item.get("region") != new_region:
                item["region"] = new_region
                dirty.add(date)
            flat.append((date, item))
    before = {
        item.get("id"): (
            item.get("cluster_id"),
            item.get("cluster_item_count"),
            item.get("cluster_source_count"),
            item.get("reddit_score"),
            item.get("reddit_comments"),
        )
        for _date, item in flat
    }
    cluster_items([item for _date, item in flat])
    refresh_reddit_stats([item for _date, item in flat])
    for date, item in flat:
        now = (
            item.get("cluster_id"),
            item.get("cluster_item_count"),
            item.get("cluster_source_count"),
            item.get("reddit_score"),
            item.get("reddit_comments"),
        )
        if before.get(item.get("id")) != now:
            dirty.add(date)
    changed_region = sum(1 for _date, item in flat if item.get("region") != item.get("source_region"))
    clusters = [item for _date, item in flat if item.get("cluster_item_count", 1) > 1]
    log(
        f"derived regions/clusters dirty_days={len(dirty)} "
        f"multi_items={len(clusters)} region_diff={changed_region}"
    )
    return dirty


def write_search(days: dict[str, list[dict]]) -> None:
    by_month: dict[str, list[dict]] = {}
    for date, items in days.items():
        month = date[:7]
        if len(month) != 7:
            continue
        bucket = by_month.setdefault(month, [])
        for item in items:
            bucket.append(
                {
                    "id": item.get("id"),
                    "date": date,
                    "published_at": item.get("published_at"),
                    "title_zh": item.get("title_zh"),
                    "title_en": item.get("title_en"),
                    "summary_zh": item.get("summary_zh"),
                    "summary_en": item.get("summary_en"),
                    "image": item.get("image"),
                    "source": item.get("source"),
                    "region": item.get("region"),
                    "tags": item.get("tags") or ["其他"],
                    "url": item.get("url"),
                    "translation_status": item.get("translation_status"),
                    "cluster_id": item.get("cluster_id"),
                    "cluster_item_count": item.get("cluster_item_count") or 1,
                    "cluster_source_count": item.get("cluster_source_count") or 1,
                    "reddit_score": item.get("reddit_score"),
                    "reddit_comments": item.get("reddit_comments"),
                }
            )
    search_dir = DATA / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    keep: set[str] = set()
    months = []
    for month, records in by_month.items():
        records.sort(key=lambda row: row.get("published_at") or "", reverse=True)
        filename = f"{month}.json"
        keep.add(filename)
        write_json(search_dir / filename, {"month": month, "count": len(records), "items": records})
        months.append({"month": month, "count": len(records), "file": f"data/search/{filename}"})
    for stale in search_dir.glob("????-??.json"):
        if stale.name not in keep:
            stale.unlink()
    months.sort(key=lambda row: row["month"], reverse=True)
    write_json(
        DATA / "search-index.json",
        {
            "updated_at": iso_shanghai(datetime.now(SHANGHAI)),
            "tags": TAG_ORDER,
            "months": months,
        },
    )


def day_of(item: dict) -> str:
    published = item.get("published_at") or ""
    if len(published) >= 10:
        return published[:10]
    return TODAY.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch odd news into data/*.json")
    parser.add_argument("--no-models", action="store_true")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--no-enrich", action="store_true")
    parser.add_argument("--rebuild-only", action="store_true")
    args = parser.parse_args()
    if args.rebuild_only:
        days = load_days()
        dirty = apply_derived(days)
        if dirty or not (DATA / "search-index.json").exists():
            write_outputs(days, dirty)
            log(f"rebuilt {len(dirty)} day file(s)")
        import retranslate

        retranslate.run()
        return 0

    log(f"odd-news fetch for Shanghai date {TODAY.isoformat()}")
    days = load_days()
    seen = known_keys(days)
    log(f"existing items: {len(seen)} across {len(days)} days")

    feed_errors: list[str] = []
    parsed_counts: list[tuple[str, int]] = []
    collected: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_feed, source) for source in SOURCES]
        fetched: list[tuple[dict, str | None, str | None]] = []
        for future in as_completed(futures):
            fetched.append(future.result())
    # Preserve source order so publisher URLs win dedupe over later Reddit copies.
    order = {source["id"]: index for index, source in enumerate(SOURCES)}
    fetched.sort(key=lambda row: order[row[0]["id"]])
    for source, text, error in fetched:
        if error or not text:
            feed_errors.append(f"{source['name']}: {error}")
            log(f"FAIL {source['name']}: {error}")
            continue
        try:
            entries = parse_feed(source, text)
            if source["kind"] == "google":
                before = len(entries)
                entries = resolve_google_entries(entries, source)
                log(f"     resolved {len(entries)}/{before} Google News links for {source['name']}")
        except Exception as exc:  # noqa: BLE001
            feed_errors.append(f"{source['name']}: parse {exc}")
            log(f"FAIL {source['name']}: parse {exc}")
            continue
        parsed_counts.append((source["name"], len(entries)))
        log(f"OK   {source['name']}: {len(entries)} entries")
        collected.extend(entries)

    new_items: list[dict] = []
    for item in collected:
        key = dedupe_key(item["url"])
        if key in seen:
            continue
        seen.add(key)
        new_items.append(item)
    log(f"new unique items: {len(new_items)}")

    dirty: set[str] = set()
    for item in new_items:
        date = day_of(item)
        days.setdefault(date, []).append(item)
        dirty.add(date)

    if not args.no_enrich:
        needing = [
            item
            for day_items in days.values()
            for item in day_items
            if needs_meta(item)
        ]
        enrich_items(needing)
        for item in needing:
            dirty.add(day_of(item))

    targets = []
    seen_ids: set[str] = set()
    pending_anywhere = [
        item
        for day_items in days.values()
        for item in day_items
        if item.get("translation_status") == "pending" or (item.get("summary_en") and not item.get("summary_zh"))
    ]
    for item in new_items + recent_items(days) + pending_anywhere:
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        status = item.get("translation_status")
        if status in {"ok", "ai"} and item.get("title_zh") and item.get("summary_zh"):
            continue
        # Machine translations stay put until a live model can replace them.
        # Committed translations are reapplied after this step.
        if status == "fallback" and (args.no_models or not models_token()):
            continue
        targets.append(item)

    use_models = False
    if not args.no_models and any(item.get("translation_status") != "ok" for item in targets):
        use_models = probe_models()
    if targets:
        before = {item["id"]: (item.get("title_zh"), item.get("translation_status")) for item in targets}
        translate_items(targets, use_models=use_models, use_fallback=not args.no_fallback)
        for item in targets:
            if (item.get("title_zh"), item.get("translation_status")) != before[item["id"]]:
                dirty.add(day_of(item))

    dirty |= apply_tags(days)
    dirty |= apply_derived(days)
    search_missing = not (DATA / "search-index.json").exists()
    if not dirty and not search_missing and (DATA / "index.json").exists():
        log("no data changes")
    else:
        write_outputs(days, dirty)
        log(f"wrote {len(dirty)} day file(s) and the search index")

    by_status: dict[str, int] = {}
    by_day: list[tuple[str, int]] = []
    for date in sorted(days.keys(), reverse=True):
        by_day.append((date, len(days[date])))
        for item in days[date]:
            status = item.get("translation_status") or "pending"
            by_status[status] = by_status.get(status, 0) + 1
    images = sum(1 for items in days.values() for item in items if item.get("image"))
    total = sum(count for _date, count in by_day)
    log("per source parsed: " + ", ".join(f"{name}={count}" for name, count in parsed_counts))
    if feed_errors:
        log("feed errors: " + " | ".join(feed_errors))
    log("days: " + ", ".join(f"{date}={count}" for date, count in by_day[:14]))
    india_recent = []
    for date, count in by_day[:6]:
        day_items = days.get(date) or []
        india = sum(1 for item in day_items if item.get("region") == "印度")
        india_recent.append(f"{date}:{india}/{count}")
    all_tags: dict[str, int] = {}
    for item_list in days.values():
        for item in item_list:
            for tag in item.get("tags") or []:
                all_tags[tag] = all_tags.get(tag, 0) + 1
    log("india recent " + ", ".join(india_recent))
    log("tags " + ", ".join(f"{tag}={all_tags.get(tag, 0)}" for tag in TAG_ORDER))
    log(
        "SUMMARY "
        f"new={len(new_items)} total={total} images={images} "
        f"status={json.dumps(by_status, ensure_ascii=False)} "
        f"feeds_ok={len(parsed_counts)} feeds_fail={len(feed_errors)}"
    )
    if not parsed_counts and not days:
        return 1
    # Reapply committed translations after the fetch so a re-fetch cannot
    # leave an applied item on the machine-translation text.
    import retranslate

    retranslate.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
