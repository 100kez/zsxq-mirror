#!/usr/bin/env python3
"""
回填历史附件的 source_file_id。
处理已有 Attachment 记录但缺少 source_file_id 的文件附件（约 1560 帖，运行约 1 小时）。
"""
import os, sys, time, random, django
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "content_sync.settings")
django.setup()

from posts.models import Attachment
from syncer.sync_zsxq import load_token, fetch_topic_detail

TYPE_MAP = {"talk": "talk", "q&a": "q", "article": "article"}
FILE_TYPES = ["document", "audio", "video", "archive", "other"]


def run():
    token = load_token()
    headers = {
        "Cookie": f"zsxq_access_token={token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://wx.zsxq.com/",
    }

    qs = (
        Attachment.objects
        .filter(source_file_id="", file_type__in=FILE_TYPES)
        .select_related("post")
        .order_by("post__published_at")
    )
    total_atts = qs.count()
    print(f"[info] 待回填附件：{total_atts} 条")

    # 按帖子分组，避免重复调 API
    by_post = defaultdict(list)
    for att in qs.iterator(chunk_size=500):
        by_post[att.post.pk].append(att)

    total_posts = len(by_post)
    print(f"[info] 涉及帖子：{total_posts} 篇\n")

    fixed = skipped = errors = 0

    for i, (post_pk, atts) in enumerate(by_post.items(), 1):
        post = atts[0].post
        if not post.source_post_id:
            skipped += len(atts)
            continue

        detail = fetch_topic_detail(post.source_post_id, headers)
        if not detail:
            errors += len(atts)
            time.sleep(random.uniform(2.0, 3.0))
            continue

        t_type = detail.get("type", "talk")
        body   = detail.get(TYPE_MAP.get(t_type, "talk"), {})
        files  = body.get("files", [])

        # filename → file_id 映射
        file_map = {
            (f.get("name") or f.get("title", "")): f.get("file_id", "")
            for f in files
        }

        for att in atts:
            fid = file_map.get(att.filename, "")
            if fid:
                att.source_file_id = fid
                att.allow_download  = True
                att.save(update_fields=["source_file_id", "allow_download"])
                fixed += 1
            else:
                skipped += 1

        if i % 50 == 0 or i == total_posts:
            print(f"  进度 {i}/{total_posts} 帖 | 已修复 {fixed} | 跳过 {skipped} | 失败 {errors}")

        time.sleep(random.uniform(4.0, 7.0))

    print(f"\n[完成] 修复 {fixed} 个附件，跳过 {skipped} 个，失败 {errors} 个")


if __name__ == "__main__":
    run()
