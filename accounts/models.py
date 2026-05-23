import secrets
import uuid
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


def _default_invite_code():
    return uuid.uuid4().hex[:16].upper()


class InviteCode(models.Model):
    code       = models.CharField('邀请码', max_length=32, unique=True, default=_default_invite_code)
    days       = models.PositiveIntegerField('授权天数', default=30,
                                             help_text='注册或续期时授予的天数')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_invites', verbose_name='创建者'
    )
    used_by    = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='used_invites', verbose_name='使用者'
    )
    used_at    = models.DateTimeField('使用时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    is_active  = models.BooleanField('是否有效', default=True)
    note       = models.CharField('备注', max_length=200, blank=True)

    class Meta:
        verbose_name = '邀请码'
        verbose_name_plural = '邀请码'
        ordering = ['-created_at']

    def __str__(self):
        status = '已使用' if self.used_by else ('有效' if self.is_active else '已禁用')
        return f'{self.code} [{status}，{self.days}天]'

    @property
    def is_usable(self):
        return self.is_active and self.used_by is None

    def redeem(self, user):
        """兑换邀请码：给用户开通/延长会员，标记已使用。"""
        membership, _ = Membership.objects.get_or_create(
            user=user,
            defaults={'expires_at': timezone.now()},
        )
        membership.add_days(self.days)
        self.used_by = user
        self.used_at = timezone.now()
        self.is_active = False
        self.save()
        return self.days


class Membership(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE,
                                      related_name='membership', verbose_name='用户')
    expires_at = models.DateTimeField('到期时间')
    note       = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '会员权限'
        verbose_name_plural = '会员权限'
        ordering = ['expires_at']

    def __str__(self):
        status = '有效' if self.is_active else '已过期'
        return f'{self.user.username} [{status}，到期 {self.expires_at.strftime("%Y-%m-%d %H:%M")}]'

    @property
    def is_active(self):
        return timezone.now() < self.expires_at

    @property
    def days_remaining(self):
        delta = self.expires_at - timezone.now()
        return max(0, delta.days)

    def add_days(self, days: int):
        base = max(self.expires_at, timezone.now())
        self.expires_at = base + timedelta(days=days)
        self.save(update_fields=['expires_at', 'updated_at'])


class PayOrder(models.Model):
    PLAN_CHOICES = [
        ('daily',   '日卡 8.8 元 / 1 天'),
        ('monthly', '月卡 88 元 / 30 天'),
    ]
    STATUS_CHOICES = [
        ('pending', '待支付'),
        ('paid',    '已支付'),
        ('failed',  '支付失败'),
        ('expired', '已过期'),
    ]

    user          = models.ForeignKey(User, on_delete=models.CASCADE,
                                      related_name='pay_orders', verbose_name='用户')
    mch_order_no  = models.CharField('商户订单号', max_length=64, unique=True)
    sys_order_no  = models.CharField('系统订单号', max_length=64, blank=True)
    plan          = models.CharField('套餐', max_length=16, choices=PLAN_CHOICES)
    amount        = models.DecimalField('金额（元）', max_digits=10, decimal_places=2)
    days          = models.PositiveIntegerField('授权天数')
    status        = models.CharField('订单状态', max_length=16,
                                     choices=STATUS_CHOICES, default='pending')
    pay_url       = models.URLField('支付链接', blank=True)
    paid_at       = models.DateTimeField('支付时间', null=True, blank=True)
    notify_payload = models.JSONField('回调原文', null=True, blank=True)
    created_at    = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at    = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '支付订单'
        verbose_name_plural = '支付订单'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.mch_order_no} [{self.get_status_display()}] {self.user.username} ¥{self.amount}'

    @staticmethod
    def new_order_no() -> str:
        return 'BD' + timezone.now().strftime('%Y%m%d%H%M%S') + uuid.uuid4().hex[:8].upper()


class EmailVerifyCode(models.Model):
    PURPOSE_CHOICES = [('register', '注册')]
    CODE_TTL_SECONDS    = 10 * 60
    RESEND_COOLDOWN_SEC = 60

    email       = models.EmailField('邮箱', db_index=True)
    code        = models.CharField('验证码', max_length=8)
    purpose     = models.CharField('用途', max_length=16, choices=PURPOSE_CHOICES, default='register')
    created_at  = models.DateTimeField('生成时间', auto_now_add=True)
    consumed_at = models.DateTimeField('消费时间', null=True, blank=True)
    ip          = models.GenericIPAddressField('请求IP', null=True, blank=True)

    class Meta:
        verbose_name = '邮箱验证码'
        verbose_name_plural = '邮箱验证码'
        ordering = ['-created_at']

    def __str__(self):
        flag = '已用' if self.consumed_at else '未用'
        return f'{self.email} {self.code} [{flag}]'

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.created_at + timedelta(seconds=self.CODE_TTL_SECONDS)

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired

    def consume(self):
        self.consumed_at = timezone.now()
        self.save(update_fields=['consumed_at'])

    @staticmethod
    def gen_code() -> str:
        return f'{secrets.randbelow(1_000_000):06d}'

    @classmethod
    def latest_for(cls, email: str, purpose: str = 'register'):
        return cls.objects.filter(email=email, purpose=purpose).order_by('-created_at').first()
