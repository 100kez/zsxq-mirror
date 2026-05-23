#!/usr/bin/env python3
"""
知识星球内容爬虫 v7 — 直接调用官方 API，支持按日期批量翻页

运行示例：
  python syncer/crawl_zsxq_with_cookie.py                    # 最新 5 条（默认）
  python syncer/crawl_zsxq_with_cookie.py --since 2026-04-01 # 4月1日至今全量
  python syncer/crawl_zsxq_with_cookie.py --since 2026-04-01 --out data/full.json

安全说明：
- Cookie 内容不会出现在任何日志或标准输出中
- 请勿将 syncer/auth/ 目录提交到 git
"""
import argparse
import json
import re
import sys
import time
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote

import requests

# ── 配置 ─────────────────────────────────────────────────────────────────────
COOKIE_FILE = Path(__file__).parent / "auth" / "zsxq_cookie.txt"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "zsxq_export_test.json"
GROUP_ID    = "48885244111858"
API_BASE    = "https://api.zsxq.com/v2"
PAGE_SIZE   = 20   # API 单页最大数量
# ─────────────────────────────────────────────────────────────────────────────

CST = timezone(timedelta(hours=8))


def load_token(path: Path) -> str:
    if not path.exists():
        print(f"[错误] Cookie 文件不存在：{path}", file=sys.stderr)
        sys.exit(1)
    raw = path.read_text(encoding="utf-8").strip()
    cookies: dict[str, str] = {}
    if "=" in raw and "\n" not in raw.strip():
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                cookies[k.strip()] = v.strip()
    else:
        for line in raw.splitlines():
            line = line.strip()
            if line and " " in line:
                k, _, v = line.partition(" ")
                cookies[k.strip()] = v.strip()
    token = cookies.get("zsxq_access_token", "")
    if not token:
        print("[错误] 未找到 zsxq_access_token，请更新 syncer/auth/zsxq_cookie.txt", file=sys.stderr)
        sys.exit(1)
    print(f"[info] zsxq_access_token 已加载（长度 {len(token)}，内容已隐藏）")
    return token


def strip_embedded(text: str) -> str:
    def replace_tag(m: re.Match) -> str:
        title_m = re.search(r'title="([^"]*)"', m.group(0))
        return unquote(title_m.group(1)) if title_m else ""
    return re.sub(r"<e\s[^>]*/?>", replace_tag, text).strip()


def parse_create_time(ts: str) -> datetime:
    """解析 API 返回的 ISO 时间字符串为 aware datetime（CST）。"""
    ts = ts.strip()
    # "2026-05-10T12:25:48.406+0800" → 标准 ISO
    ts_std = ts.replace("+0800", "+08:00")
    try:
        return datetime.fromisoformat(ts_std)
    except ValueError:
        return datetime.now(tz=CST)


def parse_topic(t: dict) -> dict | None:
    topic_id = str(t.get("topic_uid") or t.get("topic_id", ""))
    t_type   = t.get("type", "")

    if t_type == "talk":
        body = t.get("talk", {})
    elif t_type == "q&a":
        body = t.get("q", {})
    elif t_type == "article":
        body = t.get("article", {})
    else:
        body = t.get("talk", t.get("q", t.get("article", {})))

    raw_text = body.get("text", "")
    text     = strip_embedded(raw_text)
    if not text:
        return None

    author = "大笨狗"

    attachments = []
    for img in body.get("images", []):
        url = (img.get("original", {}).get("url")
               or img.get("large", {}).get("url")
               or img.get("url", ""))
        if url:
            attachments.append({
                "file_name": url.split("/")[-1].split("?")[0] or "image.jpg",
                "file_url":  url,
                "file_size": (img.get("original", {}).get("size")
                              or img.get("large", {}).get("size", 0)),
                "mime_type": "image/jpeg",
            })
    for f in body.get("files", []):
        attachments.append({
            "file_name": f.get("name", "file"),
            "file_url":  f.get("url", ""),
            "file_size": f.get("size", 0),
            "mime_type": f.get("type", "application/octet-stream"),
        })

    first_line = next((l.strip() for l in text.splitlines() if l.strip()), text[:40].strip())
    title      = (first_line[:40] + "…") if len(first_line) > 40 else first_line
    create_ts  = t.get("create_time", "")

    return {
        "source_post_id": topic_id,
        "title":          title,
        "author_name":    author,
        "published_at":   create_ts,
        "source_url":     f"https://wx.zsxq.com/topic/{topic_id}",
        "content_html":   "",
        "content_text":   text,
        "summary":        text[:150].strip(),
        "tags":           [],
        "attachments":    attachments,
    }


def fetch_page(token: str, group_id: str, end_time: str | None) -> list[dict]:
    params  = {"count": PAGE_SIZE}
    if end_time:
        params["end_time"] = end_time
    headers = {
        "Cookie":     f"zsxq_access_token={token}",
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Referer":    f"https://wx.zsxq.com/group/{group_id}",
        "Origin":     "https://wx.zsxq.com",
    }
    for attempt in range(4):
        resp = requests.get(f"{API_BASE}/groups/{group_id}/topics",
                            params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("succeeded"):
            return data.get("resp_data", {}).get("topics", [])
        code = data.get("code")
        if code == 1059:  # 频率限制，等待后重试
            wait = 10 * (attempt + 1)
            print(f"  [限速] code=1059，等待 {wait}s 后重试（第{attempt+1}次）...")
            time.sleep(wait)
            continue
        if code == 1030:
            print("[错误] Token 已失效，请重新复制 zsxq_access_token", file=sys.stderr)
        else:
            print(f"[错误] API succeeded=false  code={code}", file=sys.stderr)
        sys.exit(1)
    print("[错误] 多次重试后仍触发频率限制，退出", file=sys.stderr)
    sys.exit(1)


def run() -> None:
    parser = argparse.ArgumentParser(description="知识星球爬虫")
    parser.add_argument("--since", default=None,
                        help="同步起始日期 YYYY-MM-DD（不填则只取最新 5 条）")
    parser.add_argument("--out", default=None,
                        help="输出 JSON 路径（默认 data/zsxq_export_test.json）")
    args = parser.parse_args()

    out_file = Path(args.out) if args.out else OUTPUT_FILE
    out_file.parent.mkdir(parents=True, exist_ok=True)

    token = load_token(COOKIE_FILE)

    # 解析起始日期
    if args.since:
        since_dt = datetime(
            *[int(x) for x in args.since.split("-")], tzinfo=CST
        )
        print(f"[info] 同步范围：{args.since} 至今  group_id={GROUP_ID}")
        max_posts = None
    else:
        since_dt  = None
        max_posts = 5
        print(f"[info] 快速模式：最新 {max_posts} 条  group_id={GROUP_ID}")

    posts: list[dict] = []
    end_time: str | None = None
    page = 0
    done = False

    while not done:
        delay = random.uniform(2.0, 3.5)
        time.sleep(delay)

        raw = fetch_page(token, GROUP_ID, end_time)
        if not raw:
            print("[info] 已到末页（无更多数据）")
            break

        page += 1
        added = 0
        for t in raw:
            create_dt = parse_create_time(t.get("create_time", ""))

            # 如果有起始日期限制，过了就停
            if since_dt and create_dt < since_dt:
                done = True
                break

            p = parse_topic(t)
            if p:
                posts.append(p)
                added += 1

            # 快速模式：达到数量上限就停
            if max_posts and len(posts) >= max_posts:
                done = True
                break

        oldest = raw[-1].get("create_time", "")
        print(f"  页{page:>3}: +{added}条  累计={len(posts)}  最旧={oldest[:10]}")
        end_time = oldest

        # 翻到目标日期之前就停
        if since_dt and oldest and parse_create_time(oldest) < since_dt:
            break

    # 输出
    result = {
        "meta": {
            "source_group": f"https://wx.zsxq.com/group/{GROUP_ID}",
            "exported_at":  datetime.now().isoformat(),
            "count":        len(posts),
            "since":        args.since or "latest-5",
            "mode":         "api_v7",
        },
        "posts": posts,
    }
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[完成] 共 {len(posts)} 条 → {out_file}")

    if posts:
        print(f"  最新：{posts[0]['published_at'][:10]}  {posts[0]['title']}")
        print(f"  最旧：{posts[-1]['published_at'][:10]}  {posts[-1]['title']}")


if __name__ == "__main__":
    run()
