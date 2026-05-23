"""会员付费下单 / 异步通知 / 同步返回视图。"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import qwgua
from .models import Membership, PayOrder

logger = logging.getLogger(__name__)

PLANS: dict[str, tuple[str, Decimal, int]] = {
    'daily':   ('日卡', Decimal('8.80'),  1),
    'monthly': ('月卡', Decimal('88.00'), 30),
}


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def pricing(request):
    plans = [
        {'key': k, 'title': t, 'amount': a, 'days': d}
        for k, (t, a, d) in PLANS.items()
    ]
    return render(request, 'accounts/pricing.html', {'plans': plans})


@login_required
@require_POST
def create_order(request):
    plan_key = request.POST.get('plan', '')
    method   = request.POST.get('method', 'wechat')
    if plan_key not in PLANS:
        return HttpResponseBadRequest('未知套餐')
    if method not in settings.QWGUA_PAY_CODES:
        return HttpResponseBadRequest('未知支付方式')

    title, amount, days = PLANS[plan_key]
    order = PayOrder.objects.create(
        user=request.user,
        mch_order_no=PayOrder.new_order_no(),
        plan=plan_key,
        amount=amount,
        days=days,
        status='pending',
    )

    try:
        resp = qwgua.create_pay(
            mch_order_no=order.mch_order_no,
            amount=amount,
            title=f'bddog.cn {title}',
            ip=_client_ip(request),
            code=settings.QWGUA_PAY_CODES[method],
            body=f'{request.user.username} 购买 {title}',
        )
    except Exception as e:
        logger.exception('qwgua create_pay 异常 order=%s', order.mch_order_no)
        order.status = 'failed'
        order.save(update_fields=['status', 'updated_at'])
        return render(request, 'accounts/pay_error.html',
                      {'msg': f'下单失败：{e}'}, status=502)

    if resp.get('code') != 200:
        order.status = 'failed'
        order.save(update_fields=['status', 'updated_at'])
        return render(request, 'accounts/pay_error.html',
                      {'msg': resp.get('msg', '下单失败')}, status=502)

    data = resp.get('data', {})
    order.sys_order_no = data.get('sysOrderNo', '')
    order.pay_url      = data.get('payUrl', '')
    order.save(update_fields=['sys_order_no', 'pay_url', 'updated_at'])

    if not order.pay_url:
        return render(request, 'accounts/pay_error.html',
                      {'msg': '通道未返回支付链接'}, status=502)
    return render(request, 'accounts/pay_waiting.html', {
        'order':       order,
        'plan_title':  title,
        'method':      method,
    })


@csrf_exempt
@require_POST
def notify(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest('bad json')

    if not qwgua.verify_notify(payload):
        logger.warning('qwgua 验签失败 payload=%s', payload)
        return HttpResponseBadRequest('bad sign')

    mch_order_no = payload.get('mchOrderNo', '')
    status_code  = payload.get('status')

    try:
        with transaction.atomic():
            order = PayOrder.objects.select_for_update().get(mch_order_no=mch_order_no)
            if order.status == 'paid':
                return HttpResponse('success')
            order.notify_payload = payload
            order.sys_order_no   = payload.get('sysOrderNo', order.sys_order_no)
            if status_code == 3:
                order.status  = 'paid'
                order.paid_at = timezone.now()
                order.save(update_fields=['status', 'paid_at', 'sys_order_no',
                                          'notify_payload', 'updated_at'])
                membership, _ = Membership.objects.get_or_create(
                    user=order.user,
                    defaults={'expires_at': timezone.now()},
                )
                membership.add_days(order.days)
            else:
                order.status = 'failed'
                order.save(update_fields=['status', 'sys_order_no',
                                          'notify_payload', 'updated_at'])
    except PayOrder.DoesNotExist:
        logger.warning('qwgua 通知未知订单号 mch=%s', mch_order_no)
        return HttpResponseBadRequest('unknown order')

    return HttpResponse('success')


@login_required
def pay_return(request):
    return render(request, 'accounts/pay_return.html')


@login_required
def pay_status(request):
    """轮询接口：等待页用 JS 调，返回订单状态 + 当前会员到期日。"""
    mch_order_no = request.GET.get('order', '')
    try:
        order = PayOrder.objects.get(mch_order_no=mch_order_no, user=request.user)
    except PayOrder.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    mem = getattr(request.user, 'membership', None)
    return JsonResponse({
        'status':     order.status,
        'paid_at':    order.paid_at.isoformat() if order.paid_at else None,
        'expires_at': mem.expires_at.isoformat() if mem else None,
    })
