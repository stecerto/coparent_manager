from decimal import Decimal
from expenses.models import Expense


def calculate_family_balance(family):
    expenses = Expense.objects.filter(
        family=family,
        is_active=True
    )

    parent_a_total = Decimal("0.00")
    parent_b_total = Decimal("0.00")

    for expense in expenses:
        amount = expense.amount

        share_a = amount * (expense.parent_a_share / Decimal("100"))
        share_b = amount * (expense.parent_b_share / Decimal("100"))

        parent_a_total += share_a
        parent_b_total += share_b

    return {
        "parent_a_total": parent_a_total.quantize(Decimal("0.01")),
        "parent_b_total": parent_b_total.quantize(Decimal("0.01")),
        "difference": abs(
            parent_a_total - parent_b_total
        ).quantize(Decimal("0.01"))
    }