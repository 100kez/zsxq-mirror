"""
使用方式：
  python manage.py import_zsxq_json data/zsxq_export_test.json
  python manage.py import_zsxq_json data/zsxq_export_test.json --dry-run
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from posts.models import Attachment, Post, SyncLog


class Command(BaseCommand):
    help = "从 JSON 文件导入知识星球帖子（幂等：以 source_post_id 去重，已存在则更新）"

    def add_arguments(self, parser):
        parser.add_argument("json_file", help="JSON 文件路径")
        parser.add_argument("--dry-run", action="store_true", help="只预览，不写入数据库")

    def handle(self, *args, **options):
        json_path = Path(options["json_file"])
        dry_run = options["dry_run"]

        if not json_path.exists():
            raise CommandError(f"文件不存在: {json_path}")

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        posts_data = data.get("posts", []) if isinstance(data, dict) else data
        self.stdout.write(f"读取到 {len(posts_data)} 条帖子")

        if dry_run:
            self.stdout.write(self.style.WARNING("[dry-run] 预览模式，不写入数据库"))

        log = None
        if not dry_run:
            log = SyncLog.objects.create(
                status="running",
                notes=f"import_zsxq_json: {json_path.name}",
            )

        created_count = updated_count = error_count = 0

        for item in posts_data:
            try:
                source_id = str(item.get("source_post_id", "")).strip()
                if not source_id:
                    self.stderr.write(
                        f'[skip] 缺少 source_post_id，跳过: {item.get("title", "")[:40]}'
                    )
                    continue

                published_at = parse_datetime(item.get("published_at", "")) or timezone.now()
                if published_at and timezone.is_naive(published_at):
                    published_at = timezone.make_aware(published_at)

                defaults = {
                    "title": (item.get("title") or "无标题")[:500],
                    "author": (item.get("author_name") or "")[:100],
                    "published_at": published_at,
                    "source_url": (item.get("source_url") or "")[:1000],
                    "content_html": item.get("content_html") or "",
                    "content_text": item.get("content_text") or "",
                    "summary": (item.get("content_text") or "")[:500],
                    "is_published": True,
                }

                if dry_run:
                    exists = Post.objects.filter(source_post_id=source_id).exists()
                    action = "更新" if exists else "新建"
                    self.stdout.write(f"  [{action}] {defaults['title'][:60]}")
                    created_count += 1
                    continue

                post, created = Post.objects.update_or_create(
                    source_post_id=source_id,
                    defaults=defaults,
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

                for att in item.get("attachments", []):
                    fname = (att.get("file_name") or "")[:500]
                    furl = (att.get("file_url") or "")[:1000]
                    if not fname and not furl:
                        continue
                    fname = fname or furl.split("/")[-1].split("?")[0] or "attachment"

                    mime = att.get("mime_type") or ""
                    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                    if mime.startswith("image/") or ext in ("jpg", "jpeg", "png", "gif", "webp", "heic"):
                        ftype = "image"
                    elif mime.startswith("video/") or ext in ("mp4", "mov", "avi"):
                        ftype = "video"
                    elif mime.startswith("audio/") or ext in ("mp3", "m4a", "wav"):
                        ftype = "audio"
                    elif ext in ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv"):
                        ftype = "document"
                    elif ext in ("zip", "rar", "7z", "tar", "gz"):
                        ftype = "archive"
                    else:
                        ftype = "other"

                    Attachment.objects.get_or_create(
                        post=post,
                        filename=fname,
                        defaults={
                            "file_url": furl,
                            "file_size": att.get("file_size") or 0,
                            "file_type": ftype,
                            "allow_download": bool(furl),
                        },
                    )

            except Exception as e:
                error_count += 1
                self.stderr.write(self.style.ERROR(f"[error] {e}"))

        if not dry_run and log:
            log.status = "failed" if error_count else "success"
            log.posts_synced = created_count + updated_count
            log.finished_at = timezone.now()
            log.error_message = f"{error_count} 条失败" if error_count else ""
            log.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n完成：新建 {created_count} 条，更新 {updated_count} 条，失败 {error_count} 条"
            )
        )
