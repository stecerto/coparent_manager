from decimal import Decimal
from expenses.models import Expense

# Sostituisci completamente la funzione
from expenses.utils import get_expense_shares


def calculate_family_balance(family):
    expenses = Expense.objects.filter(family=family, is_active=True).select_related('child')

    parent_a_total = Decimal("0.00")
    parent_b_total = Decimal("0.00")

    for expense in expenses:
        share_a, share_b = get_expense_shares(expense)
        parent_a_total += share_a
        parent_b_total += share_b

    return {
        "parent_a_total": parent_a_total,
        "parent_b_total": parent_b_total,
        "difference": abs(parent_a_total - parent_b_total)
    }