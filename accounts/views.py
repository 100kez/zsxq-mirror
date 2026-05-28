import logging
from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.core.mail import send_mail
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import RegisterForm, RedeemCodeForm
from .models import EmailVerifyCode, Membership

logger = logging.getLogger(__name__)

TRIAL_MINUTES = 10  # 新注册用户(未用邀请码)的免费试用时长
ZJU_EMAIL_DOMAIN = '@zju.edu.cn'
ZJU_PERK_DAYS = 30  # 浙大邮箱注册赠送天数


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


@require_POST
def send_verify_code(request):
    email = (request.POST.get('email') or '').strip().lower()
    if not email or '@' not in email:
        return JsonResponse({'ok': False, 'err': '请填写有效邮箱'}, status=400)
    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({'ok': False, 'err': '该邮箱已被注册'}, status=400)

    latest = EmailVerifyCode.latest_for(email)
    if latest:
        elapsed = (timezone.now() - latest.created_at).total_seconds()
        if elapsed < EmailVerifyCode.RESEND_COOLDOWN_SEC:
            wait = int(EmailVerifyCode.RESEND_COOLDOWN_SEC - elapsed)
            return JsonResponse({'ok': False, 'err': f'请 {wait} 秒后再试'}, status=429)

    code = EmailVerifyCode.gen_code()
    EmailVerifyCode.objects.create(email=email, code=code, ip=_client_ip(request))

    subject = '【小菜鸡仓库】邮箱验证码'
    body = (
        f'你好，\n\n'
        f'你的注册验证码是：{code}\n\n'
        f'10 分钟内有效，请勿泄露。\n'
        f'如非本人操作，请忽略此邮件。\n\n'
        f'— bddog.cn'
    )
    try:
        send_mail(subject, body, None, [email], fail_silently=False)
    except Exception as e:
        logger.exception('发送验证码失败 email=%s', email)
        return JsonResponse({'ok': False, 'err': f'邮件发送失败：{e}'}, status=502)

    return JsonResponse({'ok': True, 'cooldown': EmailVerifyCode.RESEND_COOLDOWN_SEC})


def register(request):
    if request.user.is_authenticated:
        return redirect('posts:list')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            mem = getattr(user, 'membership', None)
            used_invite = mem is not None  # form.save() 用了邀请码会顺手建 membership

            granted_zju = False
            if user.email and user.email.lower().endswith(ZJU_EMAIL_DOMAIN):
                if mem is None:
                    mem = Membership.objects.create(
                        user=user,
                        expires_at=timezone.now(),
                        note=f'浙大邮箱注册赠送 {ZJU_PERK_DAYS} 天',
                    )
                mem.add_days(ZJU_PERK_DAYS)
                granted_zju = True

            if mem is None:
                # 既无邀请码也非浙大邮箱:发 TRIAL_MINUTES 分钟免费试用
                mem = Membership.objects.create(
                    user=user,
                    expires_at=timezone.now() + timedelta(minutes=TRIAL_MINUTES),
                    note=f'新注册 {TRIAL_MINUTES} 分钟试用',
                )
            login(request, user)

            exp = mem.expires_at.strftime('%Y-%m-%d')
            if granted_zju and used_invite:
                messages.success(request, f'注册成功！邀请码 + 浙大邮箱赠送 {ZJU_PERK_DAYS} 天已叠加，会员有效期至 {exp}。')
            elif granted_zju:
                messages.success(request, f'注册成功！浙大邮箱赠送 {ZJU_PERK_DAYS} 天会员，有效期至 {exp}。')
            elif used_invite:
                messages.success(request, f'注册成功！会员有效期至 {exp}。')
            else:
                messages.success(
                    request,
                    f'注册成功，欢迎 {user.username}！已开通 {TRIAL_MINUTES} 分钟免费试用，可继续浏览。'
                )
            return redirect('posts:list')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def membership(request):
    user = request.user
    mem  = getattr(user, 'membership', None)

    if request.GET.get('paid') == '1':
        if mem and mem.is_active:
            messages.success(request, f'支付成功！会员已开通至 {mem.expires_at.strftime("%Y-%m-%d")}。')
        else:
            messages.info(request, '订单仍在处理中，请稍候刷新。')

    if request.method == 'POST':
        form = RedeemCodeForm(request.POST)
        if form.is_valid():
            days = form._invite.redeem(user)
            mem  = user.membership          # refresh
            exp  = mem.expires_at.strftime('%Y-%m-%d')
            messages.success(request, f'兑换成功！已延长 {days} 天，新到期日：{exp}')
            return redirect('accounts:membership')
    else:
        form = RedeemCodeForm()

    return render(request, 'accounts/membership.html', {
        'membership': mem,
        'form': form,
        'now': timezone.now(),
    })
