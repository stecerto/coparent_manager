# expenses/admin.py
from django.contrib import admin
from .models import Expense, ExpenseCategory


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'child', 'expense_date', 'amount', 'status', 'created_by', 'payment_status')
    list_filter = ('status', 'payment_status', 'expense_type', 'created_by')
    search_fields = ('description', 'child__name', 'created_by__email')
    date_hierarchy = 'expense_date'
    readonly_fields = ('created_by', 'created_at', 'updated_at')

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'name', 'color')
    prepopulated_fields = {'name': ('display_name',)}
    search_fields = ('display_name', 'name')


