from django.urls import path
from .views import register_view, login_view, logout_view, activate_account, resend_activation, delete_account, \
    search_comuni_ajax, calculate_cf_api
from django.contrib.auth import views as auth_views
from . import views


app_name = "accounts"

urlpatterns = [
    path("accounts/profile/cf/calculate/", calculate_cf_api, name="calculate_cf_api"),
    #path("profile/cf/calculate/", calculate_cf_api, name="calculate_cf_api"),
    path("api/comuni/search/", search_comuni_ajax, name="search_comuni_ajax"),
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("activate/", activate_account, name="activate"),
    path("activate/resend/", resend_activation, name="resend_activation"),
    path('account-inactive/', views.account_inactive_view, name='account_inactive'),
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

# Gestione comuni (solo admin)
    path('admin/comuni/', views.comuni_admin_view, name='comuni_admin'),
    path('admin/comuni/add/', views.comune_add_view, name='comune_add'),
    path('admin/comuni/<int:pk>/edit/', views.comune_edit_view, name='comune_edit'),
    path('admin/comuni/<int:pk>/delete/', views.comune_delete_view, name='comune_delete'),
    path('admin/comuni/import/', views.comuni_import_view, name='comuni_import'),
]

