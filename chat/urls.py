from django.urls import path
from . import views
app_name = "chat"
urlpatterns = [
    path("", views.family_chat_view, name="chat_home"),
    path("message/<int:pk>/delete/", views.delete_message_view, name="delete_message"),
    path("history/<int:pk>/", views.message_history_view, name="message_history"),

]