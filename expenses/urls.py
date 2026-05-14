# expenses/urls.py
from django.urls import path
from . import views

app_name = "expenses"

urlpatterns = [
    path('', views.expenses_dashboard, name='expenses_dashboard'),
    path('list/', views.expenses_list, name='expenses_list'),
    path('add/', views.add_expense, name='add_expense'),
    path('edit/<int:pk>/', views.expense_update, name='edit_expense'),
    path('delete/<int:pk>/', views.expense_delete, name='delete_expense'),
    path('pdf/', views.download_expense_pdf, name='download_expense_pdf'),
    path('api/expenses-calendar/', views.expenses_calendar, name='expenses_calendar'),
    path('day/<str:date>/', views.expense_day_detail, name='expense_day_detail'),
    path('riepilogo_spese/', views.expenses_riepilogo_spese, name='expenses_riepilogo_spese'),

    # ✅ SOLO QUESTI DUE ENDPOINT AJAX (NESSUN <pk>!)
    path('update-status/', views.update_expense_status, name='update_status'),
    path('upload-payment-proof/', views.upload_payment_proof, name='upload_payment_proof'),
    path("api/send-rejection/", views.send_rejection_message, name="send_rejection_message"),
    path('history/<int:pk>/', views.expense_history, name='expense_history'),
]