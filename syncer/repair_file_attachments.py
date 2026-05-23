#!/usr/bin/env python3
"""
补全历史帖子的文件附件下载链接。
只处理没有文件类附件的帖子，调单条 API 取 file_id，再取下载 URL。
"""
import os, sys, time, random, django
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "content_sync.settings")
django.setup()

import requests
from posts.models import Post, Attachment
from syncer.sync_zsxq import (
    load_token, fetch_topic_detail, sync_attachments, guess_file_type, CST
)

API_BASE = "https://api.zsxq.com/v2"

TYPE_MAP = {"talk": "talk", "q&a": "q", "article": "article"}
FILE_TYPES = ['document', 'audio', 'video', 'archive', 'other']


def run():
    token = load_token()
    headers = {
        "Cookie":     f"zsxq_access_token={token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":    "https://wx.zsxq.com/",
    }

    qs = Post.objects.exclude(
        attachments__file_type__in=FILE_TYPES
    ).distinct().order_by('published_at')

    total = qs.count()
    print(f"[info] 待修复帖子：{total} 条")

    fixed = skipped = 0
    for i, post in enumerate(qs.iterator(chunk_size=100), 1):
        topic_id = post.source_post_id
        if not topic_id:
            skipped += 1
            continue

        detail = fetch_topic_detail(topic_id, headers)
        if not detail:
            skipped += 1
            time.sleep(random.uniform(2.0, 3.0))
            continue

        t_type = detail.get("type", "talk")
        body   = detail.get(TYPE_MAP.get(t_type, "talk"), {})
        files  = body.get("files", [])

        if files:
            att_count = sync_attachments(post, [], files, headers)
            if att_count:
                fixed += 1
                print(f"  [{i}/{total}] {post.title[:30]}  → {att_count} 个文件")

        # 进度汇报（每 50 条）
        if i % 50 == 0:
            print(f"  进度 {i}/{total}，已修复 {fixed} 条，跳过 {skipped} 条")

        time.sleep(random.uniform(1.5, 2.5))

    print(f"\n[完成] 共修复 {fixed} 条，跳过 {skipped} 条")


if __name__ == "__main__":
    run()
