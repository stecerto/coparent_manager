# expenses/admin.py
from django.contrib import admin
from .models import Expense, ExpenseCategory


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    # ✅ Unisci il meglio delle due versioni
    list_display = ('id', 'child', 'expense_date', 'amount', 'status', 'created_by', 'payment_state')
    list_filter = ('status', 'expense_type', 'family', 'created_by')
    search_fields = ('description', 'child__name', 'created_by__email')
    date_hierarchy = 'expense_date'
    readonly_fields = ('created_by', 'created_at', 'updated_at', 'version', 'previous_version')

    # ✅ Mostra lo stato di pagamento derivato dalla @property
    @admin.display(description="Stato Pagamento")
    def payment_state(self, obj):
        return obj.payment_state


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'name', 'color')
    search_fields = ('display_name','name')
    ordering = ('display_name',)

    # 🔒 SOLO STAFF/ADMIN può aggiungere/modificare/cancellare
    def has_add_permission(self, request):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff


