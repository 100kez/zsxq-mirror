#!/usr/bin/env python3
"""
回填含链接帖子的 content_html。
对 content_html 为空且 content_text 含 '#链接#' 的帖子重新拉取原始 API 数据并生成 HTML。

运行：
  python syncer/backfill_links.py
  python syncer/backfill_links.py --limit 50   # 先试跑50条
"""
import argparse
import os
import sys
import time
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "content_sync.settings")

import django
django.setup()

from posts.models import Post
from syncer.sync_zsxq import load_token, to_html, API_BASE, GROUP_ID
import requests


def fetch_topic_raw(topic_id: str, headers: dict) -> str:
    """拉取单篇帖子的原始 text 字段。"""
    for attempt in range(3):
        try:
            r = requests.get(f"{API_BASE}/topics/{topic_id}", headers=headers, timeout=15)
            r.raise_for_status()
            d = r.json()
            if d.get("succeeded"):
                topic = d["resp_data"]["topic"]
                t_type = topic.get("type", "talk")
                body_key = {"talk": "talk", "q&a": "q", "article": "article"}.get(t_type, "talk")
                return topic.get(body_key, {}).get("text", "")
            code = d.get("code")
            if code == 1059:
                wait = 15 * (attempt + 1)
                print(f"  [限速] code=1059，等待 {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [warn] code={code}，跳过 {topic_id}")
        except Exception as e:
            print(f"  [warn] 请求失败 {topic_id}: {e}")
        break
    return ""


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条，0=全部")
    args = parser.parse_args()

    token = load_token()
    headers = {
        "Cookie":     f"zsxq_access_token={token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":    f"https://wx.zsxq.com/group/{GROUP_ID}",
    }

    qs = Post.objects.filter(content_html="", content_text__contains="#链接#").order_by("-published_at")
    total = qs.count()
    if args.limit:
        qs = qs[:args.limit]
    print(f"[info] 共 {total} 篇待回填，本次处理 {qs.count()} 篇")

    updated = skipped = failed = 0
    for post in qs:
        time.sleep(random.uniform(1.5, 2.5))
        raw = fetch_topic_raw(post.source_post_id, headers)
        if not raw:
            failed += 1
            print(f"  [失败] {post.pk}  {post.title[:30]}")
            continue

        html = to_html(raw)
        if not html:
            skipped += 1
            continue

        post.content_html = html
        post.save(update_fields=["content_html"])
        updated += 1
        print(f"  [OK] {post.pk}  {post.title[:40]}")

    print(f"\n[完成] 成功={updated}  跳过={skipped}  失败={failed}")


if __name__ == "__main__":
    run()
