from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, StreamingHttpResponse, JsonResponse
from django.conf import settings
from urllib.parse import quote
import json
import re
import requests
from pathlib import Path
from accounts.decorators import membership_required
from .models import Post, Tag, Attachment

COOKIE_FILE = Path(__file__).resolve().parent.parent / "syncer" / "auth" / "zsxq_cookie.txt"


def _zsxq_token() -> str:
    raw = COOKIE_FILE.read_text(encoding="utf-8").strip()
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("zsxq_access_token"):
            parts = line.split(None, 1)
            if len(parts) == 2:
                return parts[1].strip()
    return ""


def post_list(request):
    user = request.user
    has_access = user.is_authenticated and (
        user.is_staff or user.is_superuser
        or (getattr(user, 'membership', None) and user.membership.is_active)
    )

    tag_slug = request.GET.get('tag')
    posts = Post.objects.filter(is_published=True).prefetch_related('tags', 'attachments')
    selected_tag = None
    if tag_slug:
        selected_tag = get_object_or_404(Tag, slug=tag_slug)
        posts = posts.filter(tags=selected_tag)
    paginator = Paginator(posts, 20)
    # 非会员/未登录强制只能看第一页
    page_num = request.GET.get('page') if has_access else 1
    page = paginator.get_page(page_num)
    tags = Tag.objects.all()

    # 预处理每个帖子的附件（prefetch 已缓存，无额外查询）
    for post in page.object_list:
        all_att = list(post.attachments.all())
        post.image_atts = [a for a in all_att if a.file_type == 'image' and (a.file_path or a.file_url)]
        post.file_atts  = [a for a in all_att if a.file_type != 'image']

    return render(request, 'posts/list.html', {
        'page_obj': page,
        'tags': tags,
        'selected_tag': selected_tag,
        'has_access': has_access,
    })


def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk, is_published=True)
    user = request.user
    has_full_access = user.is_authenticated and (
        user.is_staff or user.is_superuser
        or (getattr(user, 'membership', None) and user.membership.is_active)
    )
    if not has_full_access:
        # 非会员只能看"首页第一页"内的帖子
        first_page_ids = set(
            Post.objects.filter(is_published=True).values_list('pk', flat=True)[:20]
        )
        if post.pk not in first_page_ids:
            return render(request, 'accounts/membership_expired.html', status=403)

    all_att = post.attachments.all()
    images = [a for a in all_att if a.file_type == 'image']
    files  = [a for a in all_att if a.file_type != 'image']
    return render(request, 'posts/detail.html', {
        'post': post,
        'image_attachments': images,
        'file_attachments': files,
        'has_full_access': has_full_access,
    })


_ZSXQ_TYPE_MAP = {"talk": "talk", "q&a": "q", "article": "article"}


def _zsxq_headers(token: str) -> dict:
    return {
        "Cookie": f"zsxq_access_token={token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://wx.zsxq.com/",
        "Origin": "https://wx.zsxq.com",
    }


def _resolve_file_id(att: Attachment, headers: dict) -> str:
    """source_file_id 缺失时，从帖子详情 API 现查并回填。"""
    from syncer.sync_zsxq import fetch_topic_detail
    post = att.post
    if not post.source_post_id:
        return ""
    detail = fetch_topic_detail(post.source_post_id, headers)
    if not detail:
        return ""
    t_type = detail.get("type", "talk")
    body = detail.get(_ZSXQ_TYPE_MAP.get(t_type, "talk"), {})
    for f in body.get("files", []):
        if (f.get("name") or f.get("title", "")) == att.filename:
            fid = f.get("file_id", "")
            if fid:
                att.source_file_id = fid
                att.save(update_fields=["source_file_id"])
            return fid
    return ""


def _get_download_url(file_id: str, headers: dict) -> str:
    """调 zsxq files API 取新鲜签名下载链接。"""
    try:
        r = requests.get(
            f"https://api.zsxq.com/v2/files/{file_id}/download_url",
            headers=headers, timeout=10,
        )
        data = r.json()
        if data.get("succeeded"):
            return data["resp_data"]["download_url"]
    except Exception:
        pass
    return ""


@membership_required
def attachment_download(request, pk):
    att = get_object_or_404(Attachment, pk=pk)

    token = _zsxq_token()
    if not token:
        raise Http404

    headers = _zsxq_headers(token)

    file_id = att.source_file_id or _resolve_file_id(att, headers)
    if not file_id:
        raise Http404

    download_url = _get_download_url(file_id, headers)
    if not download_url:
        raise Http404

    try:
        upstream = requests.get(download_url, headers=headers, stream=True, timeout=60)
        upstream.raise_for_status()
    except Exception:
        raise Http404

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    response = StreamingHttpResponse(upstream.iter_content(chunk_size=8192), content_type=content_type)
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(att.filename)}"
    if "Content-Length" in upstream.headers:
        response["Content-Length"] = upstream.headers["Content-Length"]
    return response


def _bocha_search(query: str, count: int = 4, freshness: str = 'oneWeek') -> list[dict]:
    """调博查 Web Search API，返回 [{name, url, snippet, summary, siteName, datePublished}]。"""
    try:
        r = requests.post(
            settings.BOCHA_SEARCH_URL,
            headers={
                'Authorization': f'Bearer {settings.BOCHA_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={'query': query, 'freshness': freshness, 'summary': True, 'count': count},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        return (data.get('data') or {}).get('webPages', {}).get('value', []) or []
    except Exception:
        return []


def _format_search_context(results: list[dict]) -> str:
    lines = []
    for i, p in enumerate(results, 1):
        body = (p.get('summary') or p.get('snippet') or '').strip()
        body = re.sub(r'\s+', ' ', body)[:400]
        lines.append(
            f'[{i}] {p.get("name", "")}\n'
            f'    来源: {p.get("siteName", "")} | {p.get("datePublished", "")[:10]}\n'
            f'    {body}'
        )
    return '\n\n'.join(lines)


@membership_required
def ai_chat(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    post = get_object_or_404(Post, pk=pk, is_published=True)
    try:
        body = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'bad request'}, status=400)

    is_initial = body.get('initial', False)
    messages   = body.get('messages', [])

    # prefer plain text; fall back to HTML-stripped
    raw = post.content_text or re.sub(r'<[^>]+>', '', post.content_html)
    content_preview = raw[:6000]
    img_count = post.attachments.filter(file_type='image').count()
    img_note  = f'（另含{img_count}张图片）' if img_count else ''

    search_meta = {'used': False, 'count': 0}

    if is_initial:
        prompt = (
            '你是资深量化投资分析师，为读者做盘后总结。'
            '严格按以下 Markdown 格式输出，不要多余解释；每条 bullet 信息要充实、有具体逻辑或数据支撑，'
            '约 60-140 字（最后一节"推荐标的"可更长）。所有内容用中文。\n\n'
            '## 核心观点\n'
            '- 观点1：作者的核心立场 + 主要依据/数据\n'
            '- 观点2：（同上）\n'
            '- 观点3：（同上；2-4 条以覆盖帖子要点）\n\n'
            '## 背景解读\n'
            '- 行业/政策/宏观背景，帮读者建立语境\n'
            '- 帖子作者的判断逻辑链（A → B → C）\n'
            '- 与近期市场环境或同类观点的关系\n\n'
            '## 事实核查\n'
            '- ✓ 帖子中提到且可信的关键事实/数据（含具体数字）\n'
            '- ⚠ 需要核实或语焉不详的陈述\n'
            '- ✗ 明显有误的信息（如无则省略此条，不要硬凑）\n\n'
            '## 潜在影响\n'
            '- 短期（1-2 周）市场或板块影响\n'
            '- 中长期（1-3 个月）影响及驱动因素\n'
            '- 受益/受损的细分领域或链条上下游\n\n'
            '## 操作建议\n'
            '- 可关注的方向、交易思路或仓位建议（明确"不构成投资建议"）\n'
            '- 关键时间窗口、催化剂、跟踪指标\n'
            '- 主要风险点与止损/退出条件\n\n'
            '## 推荐标的\n'
            '- 标的代码或名称：120-180 字的逻辑（基本面亮点 + 催化剂 + 参考价位或观察窗口）\n'
            '（0-3 条；若帖子无明确标的，仅输出一条"暂无明确标的：建议跟踪上文方向，等具体催化剂出现"）\n\n'
            '【参考资料】\n'
            f'帖子标题：{post.title}\n'
            f'发布时间：{post.published_at.strftime("%Y-%m-%d")}\n'
            f'正文：\n{content_preview}{img_note}'
        )
        api_messages = [{'role': 'user', 'content': prompt}]
    else:
        last_user = next((m['content'] for m in reversed(messages) if m.get('role') == 'user'), '')
        query = f'{post.title} {last_user}'.strip()[:120]
        results = _bocha_search(query) if query else []
        search_meta = {'used': bool(results), 'count': len(results)}

        system = (
            f'你是量化投资分析助手，正在讨论以下帖子：\n'
            f'标题：{post.title}\n'
            f'发布时间：{post.published_at.strftime("%Y-%m-%d")}\n'
            f'内容摘要：{content_preview[:1500]}\n'
        )
        if results:
            system += (
                '\n# 联网搜索结果（与用户问题相关，可能含最新行情/新闻）\n'
                + _format_search_context(results)
                + '\n\n回答原则：\n'
                  '- 综合帖子内容与搜索结果回答；引用搜索结果时用 [1][2] 等编号标注\n'
                  '- 若搜索结果与问题相关性低，可忽略，主要依据帖子内容\n'
                  '- 用中文，简洁专业，不复述全部搜索内容'
            )
        else:
            system += '\n请用中文简洁回答，专业准确。'

        api_messages = [{'role': 'system', 'content': system}] + messages

    try:
        r = requests.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {settings.DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={'model': settings.DEEPSEEK_MODEL, 'messages': api_messages,
                  'stream': False, 'max_tokens': 4096, 'temperature': 0.4},
            timeout=90,
        )
        result = r.json()
        return JsonResponse({
            'content': result['choices'][0]['message']['content'],
            'search':  search_meta,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@membership_required
def search(request):
    query = request.GET.get('q', '').strip()
    posts = Post.objects.none()
    if query:
        posts = Post.objects.filter(
            is_published=True
        ).filter(
            Q(title__icontains=query) |
            Q(content_text__icontains=query) |
            Q(summary__icontains=query) |
            Q(author__icontains=query)
        ).distinct()
    paginator = Paginator(posts, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'posts/search.html', {'page_obj': page, 'query': query})
