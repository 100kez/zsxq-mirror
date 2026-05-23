from functools import wraps
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required


def membership_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        # 管理员无限制
        if user.is_staff or user.is_superuser:
            return view_func(request, *args, **kwargs)
        # 检查会员是否有效
        try:
            if user.membership.is_active:
                return view_func(request, *args, **kwargs)
        except Exception:
            pass
        return render(request, 'accounts/membership_expired.html', status=403)
    return wrapper
