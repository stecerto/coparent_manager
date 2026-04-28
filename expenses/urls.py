# expenses/urls.py
from django.urls import path
from .views  import (expenses_dashboard,
    expenses_riepilogo_spese,
    add_expense,
    expense_update,
    expense_delete,
    download_expense_pdf,
    expenses_calendar,
    expense_day_detail,
   # update_expense_status,
    update_status,
    expenses_list
    )

app_name = "expenses"
urlpatterns = [
    path('', expenses_dashboard, name='expenses_dashboard'),
    path("riepilogo_spese/",expenses_riepilogo_spese, name='expenses_riepilogo_spese'),
    path('add/', add_expense, name='add_expense'),
    path('edit/<int:pk>/', expense_update, name='edit_expense'),
    path('delete/<int:pk>/', expense_delete, name='delete_expense'),
    path('pdf/', download_expense_pdf, name='download_expense_pdf'),
    path("api/expenses-calendar/", expenses_calendar, name="expenses_calendar"),
    path('day/<str:date>/', expense_day_detail, name='expense_day_detail'),
   # path("<int:pk>/update-status/", update_expense_status, name="update_expense_status"),
    path("list/", expenses_list, name="expenses_list"),
    path('update-status/<int:pk>/', update_status, name='update_status'),


]