#!/usr/bin/env python3
"""Render a white-background X Chinese UI comment long-image.

The layout matches the approved comment sheet: back arrow and 帖子 header,
line icons, blue verification badge, 关注 button, reply box, and replies
with thread connectors. Replies are ordered by likes descending, with
nested replies kept under their parent.

Input JSON (also accepted on the CLI):

{
  "post": {
    "id", "url", "text", "created_at",
    "author": {"name", "username", "avatar_url", "verified"},
    "public_metrics": {"reply_count"|"reply", "repost_count"|"retweet",
                       "like_count"|"like", "bookmark_count"|"bookmark",
                       "impression_count"|"view"},
    "thumb_path": "optional local image",
    "thumb_url": "optional remote image",
    "has_video": bool
  },
  "replies": [
    {
      "id", "text", "created_at",
      "author": {"name", "username", "avatar_url", "verified"},
      "public_metrics": {...},
      "in_reply_to_id": "parent tweet id, or null"
    }
  ]
}

Usage:
  python scripts/render_comments.py item-comments.json outdir
Writes outdir/comments.png (and comments-x.html next to it).
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import shutil
import signal
import subprocess
import urllib.request
from pathlib import Path

from reply_filter import filter_replies

I = {
    "reply": "M1.751 10c0-4.42 3.584-8 8.005-8h4.366c4.49 0 7.501 3.58 7.501 8 0 4.43-3.01 8-7.5 8h-.367l-5.07 3.25c-.73.47-1.69-.06-1.69-.93V17.66A8.001 8.001 0 011.75 10zm8.005-6c-3.317 0-6.005 2.69-6.005 6 0 3.37 2.77 6.08 6.138 6.01l.351-.01h1.761v2.3l5.087-3.3h.5c3.44 0 5.5-2.71 5.5-6 0-3.31-2.69-6-6.12-6H9.756z",
    "rt": "M4.5 3.88l4.432 4.14-1.364 1.46L5.5 7.55V16c0 1.1.896 2 2 2H13v2H7.5c-2.209 0-4-1.79-4-4V7.55L1.432 9.48.068 8.02 4.5 3.88zM16.5 6H11V4h5.5c2.209 0 4 1.79 4 4v8.45l2.068-1.93 1.364 1.46-4.432 4.14-4.432-4.14 1.364-1.46 2.068 1.93V8c0-1.1-.896-2-2-2z",
    "like": "M16.697 5.5c-1.222-.06-2.679.51-3.89 2.16l-.805 1.09-.806-1.09C9.984 6.01 8.526 5.44 7.304 5.5c-1.243.07-2.349.78-2.91 1.91-.552 1.12-.633 2.78.479 4.82 1.074 1.97 3.257 4.27 7.129 6.61 3.87-2.34 6.052-4.64 7.126-6.61 1.111-2.04 1.03-3.7.477-4.82-.561-1.13-1.666-1.84-2.908-1.91zm4.187 7.69c-1.351 2.48-4.001 5.12-8.379 7.67l-.503.3-.504-.3c-4.379-2.55-7.029-5.19-8.382-7.67-1.36-2.5-1.41-4.86-.514-6.67.887-1.79 2.647-2.91 4.601-3.01 1.651-.09 3.368.56 4.798 2.01 1.429-1.45 3.146-2.1 4.796-2.01 1.954.1 3.714 1.22 4.601 3.01.896 1.81.846 4.17-.514 6.67z",
    "view": "M8.75 21V3h2v18h-2zM18 21V8.5h2V21h-2zM4 21l.004-10h2L6 21H4zm9.248 0v-7h2v7h-2z",
    "bm": "M4 4.5C4 3.12 5.119 2 6.5 2h11C18.881 2 20 3.12 20 4.5v18.44l-8-5.71-8 5.71V4.5zM6.5 4c-.276 0-.5.22-.5.5v14.56l6-4.29 6 4.29V4.5c0-.28-.224-.5-.5-.5h-11z",
    "share": "M12 2.59l5.7 5.7-1.41 1.42L13 6.41V16h-2V6.41l-3.3 3.3-1.41-1.42L12 2.59zM21 15l-.02 3.51c0 1.38-1.12 2.49-2.5 2.49H5.5C4.11 21 3 19.88 3 18.5V15h2v3.5c0 .28.22.5.5.5h12.98c.28 0 .5-.22.5-.5L19 15h2z",
    "badge": "M22.25 12c0-1.43-.88-2.67-2.19-3.34.46-1.39.2-2.9-.81-3.91s-2.52-1.27-3.91-.81c-.66-1.31-1.91-2.19-3.34-2.19s-2.67.88-3.33 2.19c-1.4-.46-2.91-.2-3.92.81s-1.26 2.52-.8 3.91c-1.31.67-2.2 1.91-2.2 3.34s.89 2.67 2.2 3.34c-.46 1.39-.21 2.9.8 3.91s2.52 1.26 3.91.81c.67 1.31 1.91 2.19 3.34 2.19s2.68-.88 3.34-2.19c1.39.45 2.9.2 3.91-.81s1.27-2.52.81-3.91c1.31-.67 2.19-1.91 2.19-3.34zm-11.71 4.2L6.8 12.46l1.41-1.42 2.26 2.26 4.8-5.23 1.47 1.36-6.2 6.77z",
    "more": "M3 12c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2zm9 2c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm7 0c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z",
    "back": "M7.414 13l5.043 5.04-1.414 1.42L3.586 12l7.457-7.46 1.414 1.42L7.414 11H21v2H7.414z",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
URL_RE = re.compile(r"https?://[^\s<]+")
PLACEHOLDER_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d1832211c213232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232ffc00011080001000103011100021100031101ffc40014000100000000000000000000000000000000ffc40014100100000000000000000000000000000000ffda000c0301000210031000003f00bf80ffd9"
)


def ic(key: str, size: float = 18.75, color: str = "#536471") -> str:
    return (
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="{color}">'
        f'<path d="{I[key]}"/></svg>'
    )


def esc(value: str | None) -> str:
    return html.escape(value or "")


def linkify(value: str | None) -> str:
    escaped = esc(value)
    return URL_RE.sub(lambda match: f'<a href="{match.group(0)}">{match.group(0)}</a>', escaped)


def fmt_num(value) -> str:
    if value is None or value == "" or value == 0:
        return ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    if number >= 100000:
        text = f"{number / 1000:.1f}万"
        return text.replace(".0万", "万")
    if number >= 10000:
        text = f"{number / 1000:.1f}K"
        return text.replace(".0K", "K")
    return f"{number:,}"


def metric(metrics: dict | None, *keys: str):
    metrics = metrics or {}
    for key in keys:
        if key in metrics and metrics[key] is not None:
            try:
                return int(metrics[key])
            except (TypeError, ValueError):
                return None
    return None


def likes_of(reply: dict) -> int:
    return metric(reply.get("public_metrics"), "like_count", "like") or 0


def bj_dt(iso: str | None) -> datetime.datetime | None:
    if not iso:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed + datetime.timedelta(hours=8)


def bj_meta(iso: str | None) -> str:
    parsed = bj_dt(iso)
    if not parsed:
        return ""
    hour = parsed.hour
    ap = "上午" if hour < 12 else "下午"
    hh = hour if 1 <= hour <= 12 else abs(hour - 12)
    if hh == 0:
        hh = 12
    return f"{ap}{hh}:{parsed.minute:02d} · {parsed.year}年{parsed.month}月{parsed.day}日"


def bj_short(iso: str | None) -> str:
    parsed = bj_dt(iso)
    if not parsed:
        return ""
    return f"{parsed.month}月{parsed.day}日"


def count_html(value) -> str:
    text = fmt_num(value)
    return f"<span>{text}</span>" if text else "<span></span>"


def acts(reply_count, repost_count, like_count, view_count) -> str:
    return (
        '<div class="acts">'
        f'<div class="a">{ic("reply")}{count_html(reply_count)}</div>'
        f'<div class="a">{ic("rt")}{count_html(repost_count)}</div>'
        f'<div class="a">{ic("like")}{count_html(like_count)}</div>'
        f'<div class="a">{ic("view")}{count_html(view_count)}</div>'
        f'<div class="a2">{ic("bm")}{ic("share")}</div></div>'
    )


def parent_id(reply: dict) -> str | None:
    parent = reply.get("in_reply_to_id") or reply.get("parent_id")
    if parent:
        return str(parent)
    for ref in reply.get("referenced_tweets") or []:
        if isinstance(ref, dict) and ref.get("type") == "replied_to" and ref.get("id"):
            return str(ref["id"])
    return None


def order_replies(replies: list[dict]) -> list[tuple[dict, bool, bool]]:
    """Likes descending. Nested replies stay under their parent.

    Each tuple is (reply, thread_continues_above, thread_continues_below).
    """
    by_id = {str(reply.get("id")): reply for reply in replies if reply.get("id")}
    children: dict[str, list[dict]] = {}
    top: list[dict] = []
    for reply in replies:
        parent = parent_id(reply)
        if parent and parent in by_id and parent != str(reply.get("id")):
            children.setdefault(parent, []).append(reply)
        else:
            top.append(reply)

    def sort_key(reply: dict) -> tuple:
        return (-likes_of(reply), reply.get("created_at") or "", str(reply.get("id") or ""))

    top.sort(key=sort_key)
    for kids in children.values():
        kids.sort(key=sort_key)

    ordered: list[tuple[dict, bool, bool]] = []

    def walk(reply: dict, is_child: bool) -> None:
        kids = children.get(str(reply.get("id")), [])
        ordered.append((reply, is_child, bool(kids)))
        for kid in kids:
            walk(kid, True)

    for reply in top:
        walk(reply, False)
    return ordered


def download(url: str, dest: Path) -> bool:
    if not url:
        return False
    if dest.exists() and dest.stat().st_size > 0:
        return True
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", UA), ("Accept", "image/avif,image/webp,image/*,*/*")]
    try:
        with opener.open(url, timeout=30) as resp, dest.open("wb") as handle:
            handle.write(resp.read())
        return dest.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001 - one broken image must not stop the sheet
        print("download fail", url, exc)
        return False


def safe_username(username: str | None) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (username or "user"))


def av_path(outdir: Path, username: str | None, url: str | None) -> str:
    dest = outdir / f"av_{safe_username(username)}.jpg"
    if url:
        local = Path(url)
        if local.is_file():
            if local.resolve() != dest.resolve():
                shutil.copyfile(local, dest)
        else:
            bigger = url.replace("_normal.", "_400x400.").replace("_bigger.", "_400x400.")
            if not download(bigger, dest):
                download(url, dest)
    if not dest.exists() or dest.stat().st_size == 0:
        dest.write_bytes(PLACEHOLDER_JPEG)
    return dest.name


def find_chrome() -> str | None:
    """Prefer the real binary. /usr/local/bin/google-chrome on this image injects a debugger port and never exits."""
    env = os.environ.get("CHROME_BIN")
    if env and Path(env).exists():
        return env
    for path in (
        "/opt/google/chrome/chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ):
        if Path(path).exists() and not Path(path).is_symlink():
            return path
        if Path(path).is_symlink() and "chrome/chrome" in os.path.realpath(path):
            return os.path.realpath(path)
    for name in ("chromium", "chromium-browser", "google-chrome-stable"):
        found = shutil.which(name)
        if found and "/usr/local/bin/google-chrome" not in found:
            return found
    return None


def _last_content_row(png_path: Path) -> tuple[int, int]:
    from PIL import Image

    image = Image.open(png_path).convert("RGB")
    width, height = image.size
    pixels = image.tobytes()
    stride = width * 3
    last = 0
    for y in range(height):
        row = pixels[y * stride : (y + 1) * stride]
        if any(byte < 245 for byte in row[::8]):
            last = y
    return last, height


def sheet_is_clipped(png_path: Path) -> bool:
    last, height = _last_content_row(png_path)
    return height - last < 16


def trim_bottom_white(png_path: Path) -> None:
    from PIL import Image

    image = Image.open(png_path).convert("RGB")
    last, height = _last_content_row(png_path)
    cropped = image.crop((0, 0, image.width, min(height, last + 28)))
    cropped.save(png_path, "PNG")


def estimate_height(payload: dict) -> int:
    post = payload.get("post") or {}
    height = 860
    if post.get("thumb_path") or post.get("thumb_url"):
        height += 560
    for reply in payload.get("replies") or []:
        text = reply.get("text") or ""
        lines = 1 + text.count("\n") + max(0, len(text) // 28)
        height += 130 + lines * 26
    return min(max(height, 1600), 14000)


def build_html(payload: dict, outdir: Path) -> str:
    post = payload["post"]
    replies, _omitted = filter_replies(list(payload.get("replies") or []))
    author = post.get("author") or {}
    metrics = post.get("public_metrics") or {}
    avatar = av_path(outdir, author.get("username"), author.get("avatar_url"))
    thumb_name = None
    thumb = post.get("thumb_path")
    if thumb and Path(thumb).is_file():
        thumb_name = "thumb.jpg"
        target = outdir / thumb_name
        if Path(thumb).resolve() != target.resolve():
            shutil.copyfile(thumb, target)
    elif post.get("thumb_url"):
        thumb_name = "thumb.jpg"
        download(post["thumb_url"], outdir / thumb_name)
        if not (outdir / thumb_name).exists():
            thumb_name = None

    badge = ic("badge", 17, "#1d9bf0") if author.get("verified") else ""
    media_html = ""
    if thumb_name:
        play = '<div class="play"></div>' if post.get("has_video") else ""
        media_html = f'<div class="media"><img src="{thumb_name}" alt="">{play}</div>'

    for reply in replies:
        reply_author = reply.get("author") or {}
        av_path(outdir, reply_author.get("username"), reply_author.get("avatar_url"))

    rows = ""
    for reply, thread_above, thread_below in order_replies(replies):
        reply_author = reply.get("author") or {}
        reply_metrics = reply.get("public_metrics") or {}
        classes = "rep nob" if thread_below else "rep"
        above = '<div class="ln up"></div>' if thread_above else ""
        below = '<div class="ln"></div>' if thread_below else ""
        reply_badge = ic("badge", 17, "#1d9bf0") if reply_author.get("verified") else ""
        avatar_file = f"av_{safe_username(reply_author.get('username'))}.jpg"
        rows += (
            f'<div class="{classes}"><div class="col">{above}'
            f'<img class="av" src="{avatar_file}" alt="">{below}</div>'
            f'<div class="bd"><div class="hd"><span class="nm">{esc(reply_author.get("name") or reply_author.get("username") or "")}</span>'
            f"{reply_badge}<span class=\"g\">@{esc(reply_author.get('username') or '')}</span>"
            f'<span class="g">·</span><span class="g">{bj_short(reply.get("created_at"))}</span>'
            f'<span class="mr">{ic("more", 18.75)}</span></div>'
            f'<div class="tx">{linkify(reply.get("text") or "")}</div>'
            f'{acts(metric(reply_metrics, "reply_count", "reply"), metric(reply_metrics, "repost_count", "retweet", "retweet_count"), metric(reply_metrics, "like_count", "like"), metric(reply_metrics, "impression_count", "view"))}'
            "</div></div>"
        )

    views = metric(metrics, "impression_count", "view")
    view_bit = f" · <b>{fmt_num(views) or '0'}</b> 查看" if views is not None else ""
    big_acts = (
        '<div class="acts">'
        f'<div class="a">{ic("reply", 22.5)}{count_html(metric(metrics, "reply_count", "reply"))}</div>'
        f'<div class="a">{ic("rt", 22.5)}{count_html(metric(metrics, "repost_count", "retweet", "retweet_count"))}</div>'
        f'<div class="a">{ic("like", 22.5)}{count_html(metric(metrics, "like_count", "like"))}</div>'
        f'<div class="a">{ic("bm", 22.5)}{count_html(metric(metrics, "bookmark_count", "bookmark"))}</div>'
        f'<div class="a2">{ic("share", 22.5)}</div></div>'
    )
    return f'''<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:#0f1419;width:600px;font-family:"Segoe UI","Helvetica Neue","PingFang SC","Noto Sans CJK SC","Noto Sans SC","WenQuanYi Micro Hei","Droid Sans Fallback","Noto Color Emoji",sans-serif;-webkit-font-smoothing:antialiased}}
.g{{color:#536471}} a{{color:#1d9bf0;text-decoration:none}}
.bar{{height:53px;display:flex;align-items:center;gap:30px;padding:0 16px;font-size:20px;font-weight:700}}
.post{{padding:12px 16px 0}} .top{{display:flex;align-items:center;gap:8px}} .avb{{width:40px;height:40px;border-radius:50%;object-fit:cover}}
.who{{flex:1;line-height:20px;font-size:15px}} .nm{{font-weight:700}} .flw{{background:#0f1419;color:#fff;font-weight:700;font-size:14px;padding:0 16px;height:32px;line-height:32px;border-radius:999px;margin-right:8px}}
.mt{{font-size:17px;line-height:24px;margin:12px 0;white-space:pre-wrap;word-break:break-word}}
.media{{position:relative;border-radius:16px;overflow:hidden;border:1px solid #cfd9de}} .media img{{display:block;width:100%}}
.play{{position:absolute;left:50%;top:50%;width:68px;height:68px;margin:-34px 0 0 -34px;border-radius:50%;background:#1d9bf0;border:4px solid #fff;display:flex;align-items:center;justify-content:center}}
.play:after{{content:"";border-left:22px solid #fff;border-top:13px solid transparent;border-bottom:13px solid transparent;margin-left:6px}}
.meta{{padding:16px 0;font-size:15px;color:#536471;border-bottom:1px solid #eff3f4}} .meta b{{color:#0f1419}}
.acts{{display:flex;justify-content:space-between;align-items:center;font-size:13px;color:#536471;margin-top:12px;max-width:100%}}
.a{{display:flex;align-items:center;gap:4px;min-width:52px}} .a2{{display:flex;gap:12px}}
.big .acts{{padding:4px 4px 12px;margin-top:12px;border-bottom:1px solid #eff3f4;font-size:14px}} .big svg{{width:22.5px;height:22.5px}}
.box{{display:flex;align-items:center;gap:8px;padding:12px 16px;border-bottom:1px solid #eff3f4}} .box .ph{{flex:1;font-size:20px;color:#536471}}
.btn{{background:#87898c;color:#fff;font-weight:700;font-size:15px;padding:0 16px;height:36px;line-height:36px;border-radius:999px}}
.rep{{display:flex;gap:8px;padding:12px 16px 4px;border-bottom:1px solid #eff3f4}} .rep.nob{{border-bottom:none}}
.col{{display:flex;flex-direction:column;align-items:center;width:40px;flex:none}} .av{{width:40px;height:40px;border-radius:50%;object-fit:cover}}
.ln{{width:2px;background:#cfd9de;flex:1;margin-top:4px;min-height:8px}} .ln.up{{flex:none;height:12px;margin:-12px 0 0}}
.bd{{flex:1;min-width:0}} .hd{{display:flex;align-items:center;gap:4px;font-size:15px;line-height:20px;white-space:nowrap;overflow:hidden}} .hd .mr{{margin-left:auto}}
.tx{{font-size:15px;line-height:20px;margin-top:2px;white-space:pre-wrap;word-break:break-word}} .rep .acts{{margin:12px 0 8px;padding-right:0}}
</style></head><body>
<div class="bar">{ic("back", 20, "#0f1419")}<span>帖子</span></div>
<div class="post big"><div class="top"><img class="avb" src="{avatar}" alt=""><div class="who"><span class="nm">{esc(author.get("name") or "")}</span> {badge}<br><span class="g">@{esc(author.get("username") or "")}</span></div><span class="flw">关注</span>{ic("more", 18.75)}</div>
<div class="mt">{linkify(post.get("text") or "")}</div>
{media_html}
<div class="meta">{bj_meta(post.get("created_at"))}{view_bit}</div>
{big_acts}
</div>
<div class="box"><img class="av" src="{avatar}" alt="" style="visibility:hidden;width:40px;height:40px"><span class="ph">发布你的回复</span><span class="btn">回复</span></div>
{rows}
</body></html>'''


def shoot(binary: str, profile: Path, height: int, raw_png: Path, html_path: Path) -> None:
    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)
    cmd = [
        binary,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",
        "--default-background-color=FFFFFFFF",
        f"--user-data-dir={profile}",
        f"--window-size=600,{height}",
        f"--screenshot={raw_png}",
        html_path.resolve().as_uri(),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        print("chrome timeout; keeping the screenshot if it was written")
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def render(payload: dict, outdir: str | Path, chrome: str | None = None) -> str:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    html_path = outdir / "comments-x.html"
    html_path.write_text(build_html(payload, outdir), encoding="utf-8")
    binary = chrome or find_chrome()
    if not binary:
        raise RuntimeError("google-chrome not found; set CHROME_BIN")
    profile = outdir / "chrome-profile"
    raw_png = outdir / "comments-raw.png"
    out_png = outdir / "comments.png"
    height = estimate_height(payload)
    for attempt in range(2):
        if raw_png.exists():
            raw_png.unlink()
        shoot(binary, profile, height, raw_png, html_path)
        if not raw_png.exists():
            raise RuntimeError(f"chrome did not write a screenshot for {html_path}")
        if not sheet_is_clipped(raw_png) or height >= 14000:
            break
        height = min(14000, int(height * 1.45) + 400)
        print("comment sheet was clipped; retrying taller", height)
    try:
        trim_bottom_white(raw_png)
    except Exception as exc:  # noqa: BLE001
        print("trim fail", exc)
    raw_png.replace(out_png)
    shutil.rmtree(profile, ignore_errors=True)
    print("wrote", out_png)
    return str(out_png)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an X comment long image")
    parser.add_argument("json_path")
    parser.add_argument("outdir")
    args = parser.parse_args()
    payload = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    render(payload, args.outdir)


if __name__ == "__main__":
    main()
