"""每日盘后 AI 总结 — 抓今日帖子喂 DeepSeek，写入置顶帖。

用法：
    python manage.py daily_summary               # 跑今天
    python manage.py daily_summary --date 2026-05-22
    python manage.py daily_summary --dry-run     # 不写库，只打印
"""
from __future__ import annotations

import argparse
import re
import time
import requests
from datetime import datetime, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape, linebreaks

from posts.models import Post


PROMPT_TEMPLATE = """你是资深量化研究员。下面是 {date} 当日小菜鸡仓库收录的全部帖子。请基于这些内容输出一份盘后总结，严格按以下 Markdown 结构，每条不超过 60 字。不要复述原文、不要写废话客套。

## 一、今日盘面
- 3-5 条，覆盖：主要指数走势、风格切换、活跃板块、资金流向

## 二、关键事件
- 3-5 条最重要的新闻/政策/公告，按重要性排序

## 三、推荐标的
- 3-6 个，格式：`代码/名称：一句话理由（核心逻辑+催化剂）`
- 没有明确推荐就写"暂无明确标的"

## 四、明日关注
- 2-4 条：值得继续盯的事件、数据、板块

## 五、风险提示
- 1-3 条潜在风险点

# 当日帖子全文
{corpus}
"""


def md_to_html(md: str) -> str:
    """极简 Markdown → HTML：## 标题、- 列表、`code`、段落。够用即可。"""
    html_lines = []
    in_list = False
    for line in md.split('\n'):
        line = line.rstrip()
        if not line:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            continue
        if line.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h2>{escape(line[3:].strip())}</h2>')
        elif line.startswith('# '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h1>{escape(line[2:].strip())}</h1>')
        elif line.startswith('- '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            text = escape(line[2:].strip())
            text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
            html_lines.append(f'<li>{text}</li>')
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(linebreaks(escape(line)))
    if in_list:
        html_lines.append('</ul>')
    return '\n'.join(html_lines)


class Command(BaseCommand):
    help = '调用 DeepSeek 总结当日帖子，更新置顶帖'

    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument('--date', help='日期 YYYY-MM-DD，默认今天（按服务器时区）')
        parser.add_argument('--dry-run', action='store_true', help='不写库，仅打印')
        parser.add_argument('--min-posts', type=int, default=10,
                            help='当日帖子数低于此阈值则跳过（避免节假日凑数）')

    def handle(self, *args, **opts):
        tz = timezone.get_current_timezone()
        if opts.get('date'):
            day = datetime.strptime(opts['date'], '%Y-%m-%d')
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
        else:
            now = timezone.localtime()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        day_str   = day_start.strftime('%Y-%m-%d')

        qs = (Post.objects
              .filter(is_published=True, is_pinned=False,
                      published_at__gte=day_start, published_at__lt=day_end)
              .order_by('published_at'))
        n = qs.count()
        self.stdout.write(f'[{day_str}] 待汇总帖子：{n} 条')

        if n < opts['min_posts']:
            self.stdout.write(self.style.WARNING(
                f'低于阈值 {opts["min_posts"]} 条，跳过本次总结'))
            return

        chunks = []
        for i, p in enumerate(qs, 1):
            body = (p.content_text or p.summary or '').strip()[:1200]
            chunks.append(f'### [{i}] {p.published_at.strftime("%H:%M")} {p.title}\n{body}\n')
        corpus = '\n'.join(chunks)
        self.stdout.write(f'  拼接 {len(corpus)} 字符')

        prompt = PROMPT_TEMPLATE.format(date=day_str, corpus=corpus)

        t0 = time.time()
        try:
            r = requests.post(
                'https://api.deepseek.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {settings.DEEPSEEK_API_KEY}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': settings.DEEPSEEK_MODEL,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': False,
                },
                timeout=180,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'DeepSeek 调用失败: {e}'))
            return

        elapsed = time.time() - t0
        usage = data.get('usage', {})
        md = data['choices'][0]['message']['content']
        self.stdout.write(f'  DeepSeek {elapsed:.1f}s | tokens={usage}')

        if opts['dry_run']:
            self.stdout.write(self.style.SUCCESS('--- DRY RUN OUTPUT ---'))
            self.stdout.write(md)
            return

        title = f'【AI 盘后总结】{day_str}'
        first_para = md.split('\n\n', 1)[0].replace('#', '').strip()[:300]
        html  = md_to_html(md)

        with transaction.atomic():
            # 取消旧的"AI 盘后总结"置顶（保留为普通帖留档）
            Post.objects.filter(is_pinned=True, source_post_id__startswith='ai-summary-')\
                        .exclude(source_post_id=f'ai-summary-{day_str}')\
                        .update(is_pinned=False)
            post, created = Post.objects.update_or_create(
                source_post_id=f'ai-summary-{day_str}',
                defaults=dict(
                    title=title,
                    author='大笨狗',
                    published_at=day_start.replace(hour=20, minute=0),
                    content_text=md,
                    content_html=html,
                    summary=first_para,
                    is_pinned=True,
                    is_published=True,
                ),
            )

        verb = '已新建' if created else '已更新'
        self.stdout.write(self.style.SUCCESS(
            f'  {verb}置顶帖 #{post.pk} {title}'))
