from django.urls import path


from .views import register_view, login_view, logout_view, activate_account

from django.contrib.auth import views as auth_views
from . import views
app_name = "accounts"
urlpatterns =[
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("activate/", activate_account, name="activate"),



    path("password_reset/",
         auth_views.PasswordResetView.as_view(
             template_name="accounts/password_reset.html"
         ),
         name="password_reset"),

    path("password_reset_done/",
         auth_views.PasswordResetDoneView.as_view(
             template_name="accounts/password_reset_done.html"
         ),
         name="password_reset_done"),

    path("reset/<uidb64>/<token>/",
         auth_views.PasswordResetConfirmView.as_view(
             template_name="accounts/password_reset_confirm.html"
         ),
         name="password_reset_confirm"),

    path("reset_done/",
         auth_views.PasswordResetCompleteView.as_view(
             template_name="accounts/password_reset_complete.html"
         ),
         name="password_reset_complete"),
]