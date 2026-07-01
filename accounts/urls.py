from django.urls import path
from .views import register_view, login_view, logout_view, activate_account, account_inactive_view, resend_activation, delete_account
from django.contrib.auth import views as auth_views
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("activate/", activate_account, name="activate"),
    path("activate/resend/", resend_activation, name="resend_activation"),
    path('account-inactive/', account_inactive_view, name='account_inactive'),
    path("delete-account/", delete_account, name="delete_account"),

    path("password_reset/",
         auth_views.PasswordResetView.as_view(
             template_name="accounts/password_reset.html",
             email_template_name='accounts/password_reset_email.txt',
             html_email_template_name='accounts/password_reset_email.html',
             subject_template_name='accounts/password_reset_subject.txt',
             success_url='/accounts/password_reset_inviata/'
         ),
         name="password_reset"),

    path("password_reset_inviata/",
         auth_views.PasswordResetDoneView.as_view(
             template_name="accounts/password_reset_inviata.html"
         ),
         name="password_reset_inviata"),

    path("reset/<uidb64>/<token>/",
         auth_views.PasswordResetConfirmView.as_view(
             template_name="accounts/password_reset_confirm.html",
             success_url='/accounts/password_reset_complete/'
         ),
         name="password_reset_confirm"),

    # ✅ AGGIUNGI QUESTA ROUTE MANCANTE
    path("password_reset_complete/",
         auth_views.PasswordResetCompleteView.as_view(
             template_name="accounts/password_reset_complete.html"
         ),
         name="password_reset_complete"),
]

