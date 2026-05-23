from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import InviteCode, Membership, PayOrder


# ── 会员管理 ──────────────────────────────────────────────────────────────────

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display   = ('user', 'expires_at', 'is_active_display', 'note', 'updated_at')
    list_filter    = ('expires_at',)
    search_fields  = ('user__username', 'user__email', 'note')
    readonly_fields = ('created_at', 'updated_at')
    fields         = ('user', 'expires_at', 'note', 'created_at', 'updated_at')
    actions        = ['add_7_days', 'add_30_days', 'add_90_days', 'add_365_days']

    @admin.display(description='状态', boolean=True)
    def is_active_display(self, obj):
        return obj.is_active

    def _add_days(self, request, queryset, days):
        for m in queryset:
            m.add_days(days)
        self.message_user(request, f'已为 {queryset.count()} 个用户延长 {days} 天。', messages.SUCCESS)

    @admin.action(description='延长 7 天')
    def add_7_days(self, request, queryset):
        self._add_days(request, queryset, 7)

    @admin.action(description='延长 30 天')
    def add_30_days(self, request, queryset):
        self._add_days(request, queryset, 30)

    @admin.action(description='延长 90 天')
    def add_90_days(self, request, queryset):
        self._add_days(request, queryset, 90)

    @admin.action(description='延长 365 天')
    def add_365_days(self, request, queryset):
        self._add_days(request, queryset, 365)


# ── 在用户详情页内嵌会员信息 ──────────────────────────────────────────────────

class MembershipInline(admin.StackedInline):
    model      = Membership
    extra      = 0
    fields     = ('expires_at', 'note')
    can_delete = False
    verbose_name = '会员权限'


class UserAdmin(BaseUserAdmin):
    inlines = [MembershipInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ── 邀请码（保留备用）────────────────────────────────────────────────────────

@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display  = ['code', 'days', 'created_by', 'used_by', 'used_at', 'is_active', 'note', 'created_at']
    list_filter   = ['is_active']
    search_fields = ['code', 'note', 'used_by__username']
    readonly_fields = ['used_by', 'used_at', 'created_at']
    list_editable = ['days', 'is_active', 'note']
    fields        = ['code', 'days', 'is_active', 'note', 'created_by', 'used_by', 'used_at', 'created_at']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ── 支付订单 ────────────────────────────────────────────────────────────────

@admin.register(PayOrder)
class PayOrderAdmin(admin.ModelAdmin):
    list_display  = ('mch_order_no', 'user', 'plan', 'amount', 'days',
                     'status', 'paid_at', 'created_at')
    list_filter   = ('status', 'plan')
    search_fields = ('mch_order_no', 'sys_order_no', 'user__username')
    readonly_fields = ('mch_order_no', 'sys_order_no', 'pay_url', 'paid_at',
                       'notify_payload', 'created_at', 'updated_at')
