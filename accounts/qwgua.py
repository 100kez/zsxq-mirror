"""qwgua 四方支付客户端：签名 / 下单 / 查单 / 验签。

签名算法（文档原文）：
    1. 过滤值为空的字段（不参与签名）；
    2. key 字典序升序；
    3. 拼接 key1=value1&key2=value2&...&keyN=valueN；
    4. 末尾直接追加商户密钥（无分隔符）；
    5. md5(...).lower()
"""
from __future__ import annotations

import hashlib
import requests
from decimal import Decimal
from django.conf import settings
from django.utils import timezone


def _stringify(v) -> str:
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, Decimal):
        return format(v, 'f')
    return str(v)


def sign(params: dict, key: str | None = None) -> str:
    key = key if key is not None else settings.QWGUA_MCH_KEY
    items = []
    for k in sorted(params.keys()):
        if k == 'sign':
            continue
        v = params[k]
        if v is None or v == '':
            continue
        items.append(f'{k}={_stringify(v)}')
    raw = '&'.join(items) + key
    return hashlib.md5(raw.encode('utf-8')).hexdigest().lower()


def _now_stamp() -> str:
    return timezone.localtime().strftime('%Y%m%d%H%M%S')


def _common_params() -> dict:
    return {
        'mchId':       settings.QWGUA_MCH_ID,
        'version':     '1.0',
        'requestTime': _now_stamp(),
    }


def create_pay(mch_order_no: str, amount: Decimal, title: str, ip: str,
               code: str,
               body: str = '', return_url: str | None = None,
               notify_url: str | None = None) -> dict:
    """调用 /rest/pay/create 下单，返回完整响应 JSON。code 为通道编码（如 1999/1888）。"""
    params = _common_params() | {
        'code':       code,
        'amount':     format(amount, 'f'),
        'mchOrderNo': mch_order_no,
        'notifyUrl':  notify_url or settings.QWGUA_NOTIFY_URL,
        'title':      title,
        'ip':         ip,
    }
    if body:
        params['body'] = body
    if return_url or settings.QWGUA_RETURN_URL:
        params['returnUrl'] = return_url or settings.QWGUA_RETURN_URL
    params['sign'] = sign(params)
    r = requests.post(f'{settings.QWGUA_BASE}/rest/pay/create',
                      json=params, timeout=15)
    r.raise_for_status()
    return r.json()


def query_pay(mch_order_no: str) -> dict:
    params = _common_params() | {'mchOrderNo': mch_order_no}
    params['sign'] = sign(params)
    r = requests.post(f'{settings.QWGUA_BASE}/rest/pay/query',
                      json=params, timeout=15)
    r.raise_for_status()
    return r.json()


def verify_notify(payload: dict) -> bool:
    """异步通知验签。比对 payload['sign'] 与重算签名。"""
    sent = payload.get('sign', '')
    if not sent:
        return False
    expected = sign(payload)
    return sent.lower() == expected.lower()
