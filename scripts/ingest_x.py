#!/usr/bin/env python3
"""Turn data/x/inbox/YYYY-MM-DD.json into site items and monthly AI files.

An outside job commits the inbox file. This script, run by GitHub Actions:

- downloads photos, video thumbnails, and avatars into assets/x/<tweet id>/
- resolves a direct mp4 URL with yt-dlp (nothing is saved for the video)
- renders assets/x/<tweet id>/comments.png
- upserts one item per post into data/YYYY-MM-DD.json
- rebuilds data/search/YYYY-MM.json and data/search-index.json

Item id is the existing site id: first 16 hex chars of sha1(normalized URL).
Video files are never written. Re-running is safe: unchanged posts skip the
screenshot, and a fresh direct URL replaces the previous one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_news
import render_comments
from reply_filter import COMMENTS_IMAGE_NOTE, FILTER_VERSION, filter_replies
from topics import TAG_ORDER, classify_text
from x_targets import assign_angle

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INBOX = DATA / "x" / "inbox"
ASSETS = ROOT / "assets" / "x"
PAGES_ORIGIN = "https://wangningashui-netizen.github.io/odd-news"
SHANGHAI = timezone(timedelta(hours=8))
UA = render_comments.UA
VIDEO_NOTE = "直链会过期。过期后用 ytdlp_command 重新解析，不要把视频文件放进仓库。"


def log(msg: str) -> None:
    print(msg, flush=True)


def site_id(url: str) -> str:
    """Same id the rest of the site uses. Translations are keyed by it."""
    return hashlib.sha1(fetch_news.dedupe_key(url).encode("utf-8")).hexdigest()[:16]


def pages_url(relative: str) -> str:
    return PAGES_ORIGIN.rstrip("/") + "/" + relative.lstrip("/")


def metric_map(raw: dict | None) -> dict:
    """Copy only counts that are actually present. Do not invent zeros."""
    raw = raw or {}
    if not isinstance(raw, dict):
        return {}
    mapping = {
        "reply_count": ("reply_count", "reply"),
        "repost_count": ("repost_count", "retweet", "retweet_count"),
        "like_count": ("like_count", "like"),
        "quote_count": ("quote_count", "quote"),
        "bookmark_count": ("bookmark_count", "bookmark"),
        "impression_count": ("impression_count", "view", "view_count"),
    }
    cleaned: dict[str, int] = {}
    for dest, keys in mapping.items():
        for key in keys:
            if key in raw and raw[key] is not None:
                try:
                    cleaned[dest] = int(raw[key])
                except (TypeError, ValueError):
                    pass
                break
    return cleaned


def photo_urls(raw: dict) -> list[str]:
    photos = raw.get("photos") or []
    if isinstance(photos, dict):
        photos = [photos]
    urls: list[str] = []
    for photo in photos:
        if isinstance(photo, str) and photo.startswith("http"):
            urls.append(photo)
        elif isinstance(photo, dict):
            url = photo.get("url") or photo.get("src") or ""
            if isinstance(url, str) and url.startswith("http"):
                urls.append(url)
    return urls


def author_of(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        "name": str(raw.get("name") or ""),
        "username": str(raw.get("username") or ""),
        "avatar_url": str(raw.get("avatar_url") or ""),
        "verified": bool(raw.get("verified")),
    }


def reply_parent(raw: dict) -> str | None:
    parent = raw.get("in_reply_to_id") or raw.get("parent_id")
    if parent:
        return str(parent)
    for ref in raw.get("referenced_tweets") or []:
        if isinstance(ref, dict) and ref.get("type") == "replied_to" and ref.get("id"):
            return str(ref["id"])
    return None


def normalize_post(raw: dict) -> dict:
    """Accept the documented inbox shape and the trial pack's older shape."""
    if not isinstance(raw, dict):
        raise ValueError("post must be an object")
    url = str(raw.get("url") or "").strip()
    tweet_id = str(raw.get("id") or "").strip()
    if not url or not tweet_id:
        raise ValueError("post needs id and url")
    video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
    meta = video.get("meta") if isinstance(video.get("meta"), dict) else {}
    thumb = raw.get("video_thumbnail") or meta.get("preview_image_url") or ""
    if "has_video" in raw:
        has_video = bool(raw.get("has_video"))
    elif "has_video" in video:
        has_video = bool(video.get("has_video"))
    else:
        has_video = bool(thumb)
    direct = raw.get("video_direct_url") or meta.get("best_variant_url") or ""
    if not isinstance(direct, str) or not direct.startswith("http"):
        direct = ""
    title = str(raw.get("title_zh") or "").strip()
    summary = str(raw.get("summary_zh") or "").strip()
    tags = [tag for tag in (raw.get("tags") or []) if tag in TAG_ORDER]
    lang = raw.get("lang")
    if lang is not None:
        lang = str(lang) or None
    replies = []
    for reply in raw.get("replies") or []:
        if not isinstance(reply, dict):
            continue
        replies.append(
            {
                "id": str(reply.get("id") or ""),
                "author": author_of(reply.get("author")),
                "text": str(reply.get("text") or ""),
                "created_at": str(reply.get("created_at") or ""),
                "public_metrics": metric_map(reply.get("public_metrics")),
                "in_reply_to_id": reply_parent(reply),
            }
        )
    normalized = {
        "id": tweet_id,
        "url": url,
        "author": author_of(raw.get("author")),
        "created_at": str(raw.get("created_at") or ""),
        "text": str(raw.get("text") or ""),
        "lang": lang,
        "public_metrics": metric_map(raw.get("public_metrics")),
        "photos": photo_urls(raw),
        "video_thumbnail": thumb if isinstance(thumb, str) else "",
        "has_video": has_video,
        "video_direct_url": direct,
        "title_zh": title,
        "summary_zh": summary,
        "tags": tags,
        "replies": replies,
    }
    angle = raw.get("angle")
    if isinstance(angle, str) and angle.strip():
        normalized["angle"] = angle.strip()
    return normalized


def load_inbox(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        raw_posts = payload
    elif isinstance(payload, dict):
        raw_posts = payload.get("posts")
        if raw_posts is None:
            raw_posts = payload.get("items") or []
    else:
        raise ValueError(f"{path.name} must be an object with posts, or a list")
    posts = []
    for index, raw in enumerate(raw_posts):
        try:
            posts.append(normalize_post(raw))
        except ValueError as exc:
            log(f"skip {path.name} post {index}: {exc}")
    return posts


def content_sha(post: dict) -> str:
    payload = {
        "text": post.get("text"),
        "metrics": post.get("public_metrics"),
        "author": post.get("author"),
        "photos": post.get("photos"),
        "thumb": post.get("video_thumbnail"),
        "has_video": post.get("has_video"),
        "title_zh": post.get("title_zh"),
        "summary_zh": post.get("summary_zh"),
        "tags": post.get("tags"),
        "replies": post.get("replies"),
        "reply_filter": FILTER_VERSION,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def download(url: str, dest: Path) -> bool:
    if not url:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return True
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body = response.read()
    except Exception as exc:  # noqa: BLE001
        log(f"download fail {url} ({exc})")
        return False
    if len(body) < 80:
        log(f"download too small {url}")
        return False
    dest.write_bytes(body)
    return True


def download_first(urls: list[str], dest: Path) -> bool:
    for url in urls:
        if url and download(url, dest):
            return True
        if dest.exists():
            dest.unlink()
    return False


def larger_photo(url: str) -> list[str]:
    if "pbs.twimg.com/media/" in url and "name=" not in url:
        joiner = "&" if "?" in url else "?"
        return [url + joiner + "name=large", url]
    return [url]


def larger_avatar(url: str) -> list[str]:
    if not url:
        return []
    bigger = url.replace("_normal.", "_400x400.").replace("_bigger.", "_400x400.")
    if bigger == url:
        return [url]
    return [bigger, url]


def resolve_video(post_url: str) -> str | None:
    """Print the direct media URL. Do not download the file."""
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-g",
        "-f",
        "b[ext=mp4]/best[ext=mp4]/best",
        "--no-playlist",
        "--no-warnings",
        post_url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except Exception as exc:  # noqa: BLE001
        log(f"yt-dlp failed {post_url} ({exc})")
        return None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        log(f"yt-dlp {post_url} -> {detail[-1] if detail else proc.returncode}")
        return None
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip().startswith("http")]
    mp4s = [line for line in lines if ".mp4" in line.split("?", 1)[0]]
    return (mp4s or lines or [None])[0]


def shanghai_stamp(iso: str) -> str:
    if not iso:
        return datetime.now(SHANGHAI).isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(SHANGHAI).isoformat(timespec="seconds")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(SHANGHAI).isoformat(timespec="seconds")


def short_title(text: str) -> str:
    line = " ".join((text or "").split())
    return line[:300]


def render_sheet(post: dict, media: Path, local_photos: list[Path], thumb: Path | None) -> Path | None:
    work = media / "_sheet"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    author = dict(post["author"])
    avatar = media / "avatar.jpg"
    if avatar.exists():
        author["avatar_url"] = str(avatar)
    replies = []
    for reply in post["replies"]:
        copied = dict(reply)
        copied_author = dict(reply.get("author") or {})
        local = media / "avatars" / f"{render_comments.safe_username(copied_author.get('username'))}.jpg"
        if local.exists():
            copied_author["avatar_url"] = str(local)
        copied["author"] = copied_author
        replies.append(copied)
    sheet_post = {
        "id": post["id"],
        "url": post["url"],
        "text": post["text"],
        "created_at": post["created_at"],
        "author": author,
        "public_metrics": post["public_metrics"],
        "has_video": bool(post.get("has_video")),
    }
    if thumb and thumb.exists():
        sheet_post["thumb_path"] = str(thumb)
    elif local_photos:
        sheet_post["thumb_path"] = str(local_photos[0])
        sheet_post["has_video"] = False
    png = render_comments.render({"post": sheet_post, "replies": replies}, work)
    dest = media / "comments.png"
    shutil.copyfile(png, dest)
    shutil.rmtree(work, ignore_errors=True)
    return dest


def hosted_author(raw_author: dict, relative: str | None) -> dict:
    author = {
        "name": raw_author.get("name") or "",
        "username": raw_author.get("username") or "",
        "verified": bool(raw_author.get("verified")),
    }
    if raw_author.get("avatar_url"):
        author["avatar_source_url"] = raw_author["avatar_url"]
    if relative:
        author["avatar_url"] = pages_url(relative)
    elif raw_author.get("avatar_url"):
        author["avatar_url"] = raw_author["avatar_url"]
    return author


def build_item(post: dict, x_payload: dict, tags: list[str], tag_source: str) -> dict:
    published = shanghai_stamp(post.get("created_at") or "")
    title_zh = (post.get("title_zh") or "").strip()
    summary_zh = (post.get("summary_zh") or "").strip()
    now = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    text = post.get("text") or ""
    image = None
    photos = x_payload.get("photos") or []
    if photos:
        image = photos[0]
    elif x_payload.get("video_thumbnail"):
        image = x_payload["video_thumbnail"]
    item = {
        "id": site_id(post["url"]),
        "url": post["url"],
        "title_en": short_title(text),
        "title_zh": title_zh or None,
        "summary_en": text,
        "summary_zh": summary_zh or None,
        "translation_status": "ai" if title_zh else "pending",
        "image": image,
        "image_checked": True,
        "page_fetched": True,
        "source": "X",
        "source_id": "x",
        "region": "印度",
        "source_region": "印度",
        "published_at": published,
        "fetched_at": now,
        "tags": tags or ["其他"],
        "tag_source": tag_source,
        "kind": "x",
        "x": x_payload,
    }
    assign_angle(item, inbox_angle=post.get("angle"))
    return item


def upsert(days: dict[str, list[dict]], item: dict) -> set[str]:
    item_id = item["id"]
    dirty: set[str] = set()
    for date in list(days):
        kept = [row for row in days[date] if row.get("id") != item_id]
        if len(kept) != len(days[date]):
            dirty.add(date)
            if kept:
                days[date] = kept
            else:
                days.pop(date, None)
    day = (item.get("published_at") or "")[:10]
    days.setdefault(day, []).append(item)
    dirty.add(day)
    return dirty


def prepare_media(post: dict) -> tuple[Path, list[str], str | None, list[dict]]:
    media = ASSETS / post["id"]
    media.mkdir(parents=True, exist_ok=True)
    author = post["author"]
    avatar_rel = None
    if download_first(larger_avatar(author.get("avatar_url") or ""), media / "avatar.jpg"):
        avatar_rel = f"assets/x/{post['id']}/avatar.jpg"
    photo_rels: list[str] = []
    local_photos: list[Path] = []
    for index, url in enumerate(post.get("photos") or [], start=1):
        dest = media / f"photo-{index}.jpg"
        if download_first(larger_photo(url), dest):
            photo_rels.append(f"assets/x/{post['id']}/photo-{index}.jpg")
            local_photos.append(dest)
    thumb_rel = None
    thumb_path = media / "video-thumb.jpg"
    if post.get("video_thumbnail") and download_first([post["video_thumbnail"]], thumb_path):
        thumb_rel = f"assets/x/{post['id']}/video-thumb.jpg"
    elif thumb_path.exists() and thumb_path.stat().st_size == 0:
        thumb_path.unlink()
    replies_out = []
    avatar_dir = media / "avatars"
    for reply in post.get("replies") or []:
        reply_author = reply.get("author") or {}
        local_rel = None
        username = reply_author.get("username") or "user"
        dest = avatar_dir / f"{render_comments.safe_username(username)}.jpg"
        if download_first(larger_avatar(reply_author.get("avatar_url") or ""), dest):
            local_rel = f"assets/x/{post['id']}/avatars/{dest.name}"
        copied = dict(reply)
        copied["author"] = hosted_author(reply_author, local_rel)
        replies_out.append(copied)
    return media, photo_rels, thumb_rel, replies_out


def x_payload(post: dict, photo_rels: list[str], thumb_rel: str | None, replies: list[dict], video_url: str | None, video_source: str | None) -> dict:
    author_rel = f"assets/x/{post['id']}/avatar.jpg"
    author = hosted_author(post["author"], author_rel if (ASSETS / post["id"] / "avatar.jpg").exists() else None)
    comments_rel = f"assets/x/{post['id']}/comments.png"
    comments = pages_url(comments_rel) if (ASSETS / post["id"] / "comments.png").exists() else None
    now = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    kept_replies, omitted = filter_replies(replies)
    payload = {
        "post_id": post["id"],
        "lang": post.get("lang"),
        "text": post.get("text") or "",
        "author": author,
        "created_at": post.get("created_at") or "",
        "public_metrics": post.get("public_metrics") or {},
        "photos": [pages_url(rel) for rel in photo_rels],
        "video_thumbnail": pages_url(thumb_rel) if thumb_rel else None,
        "has_video": bool(post.get("has_video")),
        "video_url": video_url,
        "video_url_resolved_at": now if video_url else None,
        "video_url_source": video_source if video_url else None,
        "video_url_note": VIDEO_NOTE if post.get("has_video") else None,
        "post_url": post["url"],
        "ytdlp_command": "yt-dlp " + post["url"],
        "comments_image": comments,
        "comments_image_note": COMMENTS_IMAGE_NOTE,
        "replies": kept_replies,
        "replies_omitted": omitted,
        "content_sha": content_sha(post),
    }
    return payload


def process_post(post: dict, days: dict[str, list[dict]], force_render: bool) -> set[str]:
    sha = content_sha(post)
    previous = None
    for items in days.values():
        for item in items:
            if item.get("kind") == "x" and (item.get("x") or {}).get("post_id") == post["id"]:
                previous = item
                break
    comments_ready = (ASSETS / post["id"] / "comments.png").exists()
    same = previous and (previous.get("x") or {}).get("content_sha") == sha and comments_ready
    media, photo_rels, thumb_rel, replies = prepare_media(post)
    if not same or force_render:
        thumb = media / "video-thumb.jpg"
        local_photos = [media / f"photo-{i}.jpg" for i in range(1, len(photo_rels) + 1)]
        try:
            render_sheet(post, media, [path for path in local_photos if path.exists()], thumb if thumb.exists() else None)
        except Exception as exc:  # noqa: BLE001
            log(f"render fail {post['id']}: {exc}")
    video_url = None
    video_source = None
    if post.get("has_video"):
        video_url = resolve_video(post["url"])
        if video_url:
            video_source = "yt-dlp"
        elif post.get("video_direct_url"):
            video_url = post["video_direct_url"]
            video_source = "inbox"
            log(f"video fallback to inbox url for {post['id']}")
        elif previous and (previous.get("x") or {}).get("video_url"):
            video_url = previous["x"]["video_url"]
            video_source = (previous.get("x") or {}).get("video_url_source") or "previous"
            log(f"kept previous video url for {post['id']}")
    payload = x_payload(post, photo_rels, thumb_rel, replies, video_url, video_source)
    tags = list(post.get("tags") or [])
    tag_source = "inbox"
    if not tags:
        tags = classify_text(short_title(post.get("text") or ""), post.get("text") or "")
        tag_source = "rules"
    if previous and previous.get("tag_source") == "model" and previous.get("tags"):
        tags = previous["tags"]
        tag_source = "model"
    item = build_item(post, payload, tags, tag_source)
    if previous:
        for key in ("cluster_id", "cluster_item_count", "cluster_source_count"):
            if previous.get(key) is not None:
                item[key] = previous[key]
    log(
        f"X {post['id']} site={item['id']} photos={len(photo_rels)} "
        f"replies={len(replies)} video={'yes' if video_url else 'no'}"
    )
    return upsert(days, item)


def inbox_files(only: str | None) -> list[Path]:
    if only:
        path = Path(only)
        if not path.is_file():
            path = INBOX / only
        if not path.is_file():
            raise SystemExit(f"inbox file not found: {only}")
        return [path]
    return sorted(INBOX.glob("????-??-??.json"))


def ingest(only: str | None, force_render: bool) -> int:
    files = inbox_files(only)
    if not files:
        log("no inbox files")
        return 0
    if not render_comments.find_chrome():
        log("google-chrome not found; set CHROME_BIN")
        return 1
    days = fetch_news.load_days()
    dirty: set[str] = set()
    count = 0
    for path in files:
        posts = load_inbox(path)
        log(f"{path.name}: {len(posts)} posts")
        for post in posts:
            dirty |= process_post(post, days, force_render)
            count += 1
    if not count:
        log("inbox had no usable posts")
        return 0
    dirty |= fetch_news.recluster(days)
    fetch_news.write_outputs(days, dirty)
    log(f"ingested {count} X post(s), rewrote {len(dirty)} day file(s)")
    return 0


def refresh_videos(days_back: int) -> int:
    days = fetch_news.load_days()
    cutoff = (datetime.now(SHANGHAI).date() - timedelta(days=days_back)).isoformat()
    dirty: set[str] = set()
    checked = 0
    updated = 0
    for date, items in days.items():
        if date < cutoff:
            continue
        for item in items:
            if item.get("kind") != "x":
                continue
            payload = item.get("x") or {}
            if not payload.get("has_video"):
                continue
            post_url = payload.get("post_url") or item.get("url")
            if not post_url:
                continue
            checked += 1
            fresh = resolve_video(post_url)
            if not fresh:
                log(f"refresh miss {payload.get('post_id') or item.get('id')}")
                continue
            if payload.get("video_url") == fresh and payload.get("video_url_source") == "yt-dlp":
                continue
            payload["video_url"] = fresh
            payload["video_url_resolved_at"] = datetime.now(SHANGHAI).isoformat(timespec="seconds")
            payload["video_url_source"] = "yt-dlp"
            payload["video_url_note"] = VIDEO_NOTE
            item["x"] = payload
            dirty.add(date)
            updated += 1
    if dirty:
        fetch_news.write_outputs(days, dirty)
    log(f"refreshed video urls checked={checked} updated={updated}")
    return 0


def rerender_comments() -> int:
    """Redraw comment sheets from the inbox and files already in assets/x.

    Does not download media and does not resolve video URLs. Replies that
    fail the comment filter are left out of the image.
    """
    if not render_comments.find_chrome():
        log("google-chrome not found; set CHROME_BIN")
        return 1
    drawn = 0
    for path in inbox_files(None):
        posts = load_inbox(path)
        log(f"rerender {path.name}: {len(posts)} posts")
        for post in posts:
            media = ASSETS / post["id"]
            if not media.exists():
                log(f"skip render {post['id']}: no local media")
                continue
            thumb = media / "video-thumb.jpg"
            local_photos = sorted(media.glob("photo-*.jpg"))
            try:
                render_sheet(post, media, local_photos, thumb if thumb.exists() else None)
            except Exception as exc:  # noqa: BLE001
                log(f"render fail {post['id']}: {exc}")
                return 1
            drawn += 1
    log(f"rerendered {drawn} comment sheet(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest X inbox posts into the India library")
    parser.add_argument("--inbox", help="One inbox JSON path or file name. Default: every data/x/inbox/YYYY-MM-DD.json")
    parser.add_argument("--refresh-videos", type=int, metavar="DAYS", help="Re-resolve direct mp4 URLs for X items in the last N days")
    parser.add_argument("--force-render", action="store_true", help="Render comment sheets even when the post body is unchanged")
    parser.add_argument("--rerender-comments", action="store_true", help="Redraw comment sheets from local files. Does not download or resolve video.")
    parser.add_argument("--skip-retranslate", action="store_true")
    args = parser.parse_args()
    if args.rerender_comments and not args.inbox and args.refresh_videos is None and not args.force_render:
        return rerender_comments()
    if args.refresh_videos is not None and not args.inbox and not args.force_render:
        # Refresh-only when that flag is the operation. Combining both is allowed
        # by passing --inbox as well; the default with only --refresh-videos
        # does not re-render.
        if "--inbox" not in sys.argv:
            code = refresh_videos(args.refresh_videos)
            if code == 0 and not args.skip_retranslate:
                import retranslate

                retranslate.run()
            return code
    code = ingest(args.inbox, args.force_render)
    if args.refresh_videos is not None and code == 0:
        code = refresh_videos(args.refresh_videos)
    if code == 0 and not args.skip_retranslate:
        import retranslate

        retranslate.run()
    return code


if __name__ == "__main__":
    sys.exit(main())
