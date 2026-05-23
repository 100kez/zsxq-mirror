from django.urls import path
from . import views

app_name = 'posts'

urlpatterns = [
    path('', views.post_list, name='list'),
    path('<int:pk>/', views.post_detail, name='detail'),
    path('<int:pk>/ai/', views.ai_chat, name='ai_chat'),
    path('search/', views.search, name='search'),
    path('attachment/<int:pk>/download/', views.attachment_download, name='attachment_download'),
]
