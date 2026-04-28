from django.contrib import admin
from .models import Expense, ExpenseDocument

admin.site.register(Expense)
admin.site.register(ExpenseDocument)