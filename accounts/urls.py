from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views, payment_views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', views.register, name='register'),
    path('send-code/', views.send_verify_code, name='send_code'),
    path('membership/', views.membership, name='membership'),
    path('pricing/', payment_views.pricing, name='pricing'),
    path('pay/create/', payment_views.create_order, name='pay_create'),
    path('pay/notify/', payment_views.notify, name='pay_notify'),
    path('pay/return/', payment_views.pay_return, name='pay_return'),
    path('pay/status/', payment_views.pay_status, name='pay_status'),
]
