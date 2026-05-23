from django.db import models
from django.utils import timezone


class Tag(models.Model):
    name = models.CharField('标签名', max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '标签'
        verbose_name_plural = '标签'
        ordering = ['name']

    def __str__(self):
        return self.name


class Post(models.Model):
    source_post_id = models.CharField('原帖 ID', max_length=64, unique=True, blank=True, default='')
    title = models.CharField('标题', max_length=500)
    author = models.CharField('作者', max_length=100, blank=True)
    published_at = models.DateTimeField('发布时间', default=timezone.now)
    source_url = models.URLField('原帖链接', max_length=1000, blank=True)
    content_html = models.TextField('正文 HTML', blank=True)
    content_text = models.TextField('正文纯文本', blank=True)
    summary = models.TextField('摘要', max_length=500, blank=True)
    tags = models.ManyToManyField(Tag, verbose_name='标签', blank=True)
    created_at = models.DateTimeField('入库时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    is_published = models.BooleanField('是否发布', default=True)
    is_pinned    = models.BooleanField('置顶', default=False, db_index=True)

    class Meta:
        verbose_name = '帖子'
        verbose_name_plural = '帖子'
        ordering = ['-is_pinned', '-published_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('posts:detail', args=[self.pk])


class Attachment(models.Model):
    FILE_TYPE_CHOICES = [
        ('image', '图片'),
        ('video', '视频'),
        ('audio', '音频'),
        ('document', '文档'),
        ('archive', '压缩包'),
        ('other', '其他'),
    ]

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='attachments', verbose_name='所属帖子')
    filename = models.CharField('文件名', max_length=500)
    file_path = models.FileField('文件路径', upload_to='attachments/%Y/%m/', blank=True)
    file_url = models.URLField('文件 URL', max_length=1000, blank=True)
    source_file_id = models.CharField('知识星球文件ID', max_length=100, blank=True)
    file_size = models.PositiveIntegerField('文件大小(字节)', default=0)
    file_type = models.CharField('文件类型', max_length=20, choices=FILE_TYPE_CHOICES, default='other')
    allow_download = models.BooleanField('允许下载', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '附件'
        verbose_name_plural = '附件'

    def __str__(self):
        return self.filename

    @property
    def file_size_display(self):
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'


class SyncLog(models.Model):
    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('running', '同步中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]

    started_at = models.DateTimeField('开始时间', auto_now_add=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    posts_synced = models.IntegerField('同步帖子数', default=0)
    attachments_synced = models.IntegerField('同步附件数', default=0)
    error_message = models.TextField('错误信息', blank=True)
    notes = models.TextField('备注', blank=True)

    class Meta:
        verbose_name = '同步日志'
        verbose_name_plural = '同步日志'
        ordering = ['-started_at']

    def __str__(self):
        return f'同步 {self.started_at.strftime("%Y-%m-%d %H:%M")} [{self.get_status_display()}]'
