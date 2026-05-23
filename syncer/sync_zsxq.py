#!/usr/bin/env python3
"""
知识星球全量同步脚本 — 边爬边入库，支持附件

附件策略：
  - 图片（非头像）：下载保存到 media/attachments/，展示在页面
  - 其他文件（PDF/Word等）：只存文件名 + 原始下载链接，不占磁盘

运行：
  python syncer/sync_zsxq.py --since 2026-04-01
"""
import argparse
import hashlib
import io
import mimetypes
import os
import re
import sys
import time
import random
import django
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

# ── Django 初始化 ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "content_sync.settings")
django.setup()

from django.core.files.base import ContentFile  # noqa: E402
from posts.models import Post, Attachment        # noqa: E402

import requests  # noqa: E402

# ── 配置 ─────────────────────────────────────────────────────────────────────
COOKIE_FILE = ROOT / "syncer" / "auth" / "zsxq_cookie.txt"
GROUP_ID    = "48885244111858"
API_BASE    = "https://api.zsxq.com/v2"
PAGE_SIZE   = 20
CST         = timezone(timedelta(hours=8))
# 头像 URL 特征（跳过下载）
AVATAR_PATTERNS = re.compile(r"avatar|icon|logo|emoji|sticker|profile", re.I)
# ─────────────────────────────────────────────────────────────────────────────


def load_token() -> str:
    raw = COOKIE_FILE.read_text(encoding="utf-8").strip()
    cookies: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if line and " " in line:
            k, _, v = line.partition(" ")
            cookies[k.strip()] = v.strip()
    if "=" in raw and "\n" not in raw:
        for part in raw.split(";"):
            if "=" in part:
                k, _, v = part.strip().partition("=")
                cookies[k.strip()] = v.strip()
    token = cookies.get("zsxq_access_token", "")
    if not token:
        print("[错误] 未找到 zsxq_access_token", file=sys.stderr)
        sys.exit(1)
    print(f"[info] token 已加载（长度 {len(token)}，内容隐藏）")
    return token


def strip_embedded(text: str) -> str:
    def rep(m):
        t = re.search(r'title="([^"]*)"', m.group(0))
        return unquote(t.group(1)) if t else ""
    return re.sub(r"<e\s[^>]*/?>", rep, text).strip()


def to_html(raw_text: str) -> str:
    """Convert raw zsxq text (with <e .../> tags) to HTML, preserving web links as <a> tags."""
    def rep(m):
        tag = m.group(0)
        e_type = re.search(r'type="([^"]*)"', tag)
        href   = re.search(r'href="([^"]*)"', tag)
        title  = re.search(r'title="([^"]*)"', tag)
        label  = unquote(title.group(1)) if title else ""
        if e_type and e_type.group(1) == "web" and href:
            url = unquote(href.group(1))
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
        return label

    html = re.sub(r"<e\s[^>]*/?>", rep, raw_text).strip()
    paragraphs = re.split(r"\n{2,}", html)
    if len(paragraphs) > 1:
        return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())
    return html.replace("\n", "<br>")


def parse_dt(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.strip().replace("+0800", "+08:00"))
    except Exception:
        return datetime.now(tz=CST)


def guess_file_type(filename: str, mime: str = "") -> str:
    ext = Path(filename).suffix.lower()
    if mime.startswith("image/") or ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"):
        return "image"
    if mime.startswith("video/") or ext in (".mp4", ".mov", ".avi"):
        return "video"
    if mime.startswith("audio/") or ext in (".mp3", ".m4a", ".wav"):
        return "audio"
    if ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md"):
        return "document"
    if ext in (".zip", ".rar", ".7z", ".tar", ".gz"):
        return "archive"
    return "other"


def download_image(url: str, headers: dict) -> bytes | None:
    """下载图片，失败返回 None。"""
    try:
        r = requests.get(url, headers=headers, timeout=20, stream=True)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"    [warn] 图片下载失败: {e}")
    return None


def url_to_filename(url: str) -> str:
    """从 URL 提取文件名，去掉 query string。"""
    path = urlparse(url).path
    name = path.split("/")[-1] or "image.jpg"
    # 去掉星球图片 CDN 的参数式后缀（如 xxx?imageMogr2/...）
    name = name.split("?")[0]
    if "." not in name:
        name += ".jpg"
    return name


def sync_attachments(post: Post, images: list, files: list, img_headers: dict) -> int:
    """同步帖子附件，返回处理数量。"""
    count = 0

    # ── 图片：下载保存 ────────────────────────────────────────────────────────
    for img in images:
        url = (img.get("original", {}).get("url")
               or img.get("large", {}).get("url")
               or img.get("url", ""))
        if not url or AVATAR_PATTERNS.search(url):
            continue

        filename = url_to_filename(url)
        # 用 URL 哈希去重（避免重复下载同一张图）
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        if Attachment.objects.filter(post=post, filename=filename).exists():
            continue

        data = download_image(url, img_headers)
        if not data:
            # 下载失败就退化为只存链接
            Attachment.objects.get_or_create(
                post=post, filename=filename,
                defaults=dict(file_url=url, file_type="image",
                              file_size=0, allow_download=True)
            )
        else:
            att = Attachment(
                post=post, filename=filename,
                file_type="image",
                file_size=len(data),
                allow_download=True,
            )
            att.file_path.save(filename, ContentFile(data), save=True)
            print(f"    [图片] {filename} ({len(data)//1024}KB)")
        count += 1

    # ── 其他文件：同步时取一次下载链接存储，用户点击直接跳转 ────────────────
    for f in files:
        fname   = f.get("name", "") or f.get("title", "file")
        file_id = f.get("file_id")
        fsize   = f.get("size", 0)
        ftype   = guess_file_type(fname)

        if not fname or Attachment.objects.filter(post=post, filename=fname).exists():
            continue

        Attachment.objects.create(
            post=post,
            filename=fname,
            source_file_id=file_id or "",
            file_size=fsize,
            file_type=ftype,
            allow_download=bool(file_id),
        )
        print(f"    [文件] {fname}  {ftype}")
        count += 1

    return count


def fetch_page(token: str, end_time: str | None) -> list[dict]:
    params  = {"count": PAGE_SIZE}
    if end_time:
        params["end_time"] = end_time
    headers = {
        "Cookie":     f"zsxq_access_token={token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":    f"https://wx.zsxq.com/group/{GROUP_ID}",
    }
    for attempt in range(5):
        r = requests.get(f"{API_BASE}/groups/{GROUP_ID}/topics",
                         params=params, headers=headers, timeout=20)
        r.raise_for_status()
        d = r.json()
        if d.get("succeeded"):
            return d.get("resp_data", {}).get("topics", [])
        code = d.get("code")
        if code == 1059:
            wait = 15 * (attempt + 1)
            print(f"  [限速] code=1059，等待 {wait}s...")
            time.sleep(wait)
            continue
        if code == 1030:
            print("[错误] Token 失效，请更新 zsxq_cookie.txt", file=sys.stderr)
        else:
            print(f"[错误] API code={code}", file=sys.stderr)
        sys.exit(1)
    print("[错误] 重试耗尽", file=sys.stderr)
    sys.exit(1)


def fetch_topic_detail(topic_id: str, headers: dict) -> dict:
    """调单条接口获取帖子详情（含文件附件的 file_id）。"""
    for attempt in range(3):
        try:
            r = requests.get(f"{API_BASE}/topics/{topic_id}", headers=headers, timeout=15)
            r.raise_for_status()
            d = r.json()
            if d.get("succeeded"):
                return d.get("resp_data", {}).get("topic", {})
            code = d.get("code")
            if code == 1059:
                wait = 10 * (attempt + 1)
                print(f"  [限速] 详情接口 code=1059，等待 {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [warn] 详情接口 code={code}，跳过 {topic_id}")
        except Exception as e:
            print(f"  [warn] 获取帖子详情失败 {topic_id}: {e}")
        break
    return {}


def upsert_topic(t: dict, img_headers: dict) -> tuple[bool, str]:
    """写入帖子 + 附件，返回 (is_new, title)。"""
    topic_id = str(t.get("topic_uid") or t.get("topic_id", ""))
    t_type   = t.get("type", "")
    body     = t.get({"talk": "talk", "q&a": "q", "article": "article"}.get(t_type, "talk"), {})

    raw_text = body.get("text", "")
    text     = strip_embedded(raw_text)
    if not text:
        return False, ""

    author     = "大笨狗"
    create_ts  = t.get("create_time", "")
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), text[:40])
    title      = (first_line[:40] + "…") if len(first_line) > 40 else first_line
    html       = to_html(raw_text)

    post, created = Post.objects.update_or_create(
        source_post_id=topic_id,
        defaults=dict(
            title        = title,
            author       = author,
            published_at = parse_dt(create_ts),
            source_url   = f"https://wx.zsxq.com/topic/{topic_id}",
            content_text = text,
            content_html = html,
            summary      = text[:150],
            is_published = True,
        ),
    )

    # 附件
    images = body.get("images", [])
    files  = body.get("files", [])

    # 列表接口 files 始终为空；仅对新帖调单条接口补取附件
    if not files and created:
        time.sleep(random.uniform(1.0, 2.0))
        detail = fetch_topic_detail(topic_id, img_headers)
        d_body = detail.get(
            {"talk": "talk", "q&a": "q", "article": "article"}.get(t_type, "talk"), {}
        )
        files = d_body.get("files", [])

    if images or files:
        att_count = sync_attachments(post, images, files, img_headers)
        if att_count:
            print(f"    → {att_count} 个附件")

    return created, title


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-04-01", help="起始日期 YYYY-MM-DD")
    args = parser.parse_args()

    since_dt = datetime(*[int(x) for x in args.since.split("-")], tzinfo=CST)
    print(f"[info] 同步范围：{args.since} 至今")

    token = load_token()
    img_headers = {
        "Cookie":     f"zsxq_access_token={token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":    "https://wx.zsxq.com/",
    }

    end_time  = None
    page      = 0
    total_new = total_upd = 0

    while True:
        time.sleep(random.uniform(2.5, 4.0))

        topics = fetch_page(token, end_time)
        if not topics:
            print("[info] 无更多数据，结束")
            break

        page += 1
        page_new = page_upd = 0
        stop = False

        for t in topics:
            ct = parse_dt(t.get("create_time", ""))
            if ct < since_dt:
                stop = True
                break
            created, title = upsert_topic(t, img_headers)
            if title:
                if created:
                    page_new += 1
                    print(f"  [新] {t['create_time'][:10]}  {title}")
                else:
                    page_upd += 1

        total_new += page_new
        total_upd += page_upd
        oldest = topics[-1].get("create_time", "")
        print(f"页{page:>3}: 新增{page_new} 更新{page_upd}  累计新增={total_new}  最旧={oldest[:10]}")

        if stop or (oldest and parse_dt(oldest) < since_dt):
            print(f"[info] 已到达 {args.since}，停止")
            break

        end_time = oldest

    print(f"\n[完成] 新增 {total_new} 条，更新 {total_upd} 条")


if __name__ == "__main__":
    run()
