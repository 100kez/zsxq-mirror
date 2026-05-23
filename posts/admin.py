from django.contrib import admin
from .models import Post, Attachment, Tag, SyncLog


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ['filename', 'file_type', 'file_size', 'allow_download', 'file_url']


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'source_post_id', 'published_at', 'is_published', 'created_at']
    list_filter = ['is_published', 'tags', 'published_at']
    search_fields = ['title', 'author', 'content_text', 'summary']
    filter_horizontal = ['tags']
    date_hierarchy = 'published_at'
    inlines = [AttachmentInline]
    list_editable = ['is_published']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = [
        ('基本信息', {'fields': ['source_post_id', 'title', 'author', 'published_at', 'source_url', 'is_published', 'tags']}),
        ('内容', {'fields': ['summary', 'content_html', 'content_text']}),
        ('时间戳', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'post', 'file_type', 'file_size_display', 'allow_download']
    list_filter = ['file_type', 'allow_download']
    search_fields = ['filename', 'post__title']
    raw_id_fields = ['post']

    def file_size_display(self, obj):
        return obj.file_size_display
    file_size_display.short_description = '文件大小'


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ['started_at', 'status', 'posts_synced', 'attachments_synced', 'finished_at']
    list_filter = ['status']
    readonly_fields = ['started_at', 'finished_at', 'posts_synced', 'attachments_synced']
