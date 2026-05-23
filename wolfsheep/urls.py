from django.urls import path
from . import views

app_name = "wolfsheep"

urlpatterns = [
    path("", views.board_page, name="board"),
    path("move/", views.api_move, name="api_move"),
]
