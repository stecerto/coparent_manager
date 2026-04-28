from expenses.models import Expense


def create_expense(family, user, data):
    return Expense.objects.create(
        family=family,
        created_by=user,
        description=data.get("description"),
        expense_type=data.get("expense_type", "other"),
        amount=data.get("amount"),
        expense_date=data.get("expense_date"),
        parent_a_share=data.get("parent_a_share", 50),
        parent_b_share=data.get("parent_b_share", 50),
    )


def update_expense(expense, user, data):
    """
    NON modifica la spesa → crea nuova versione
    """
    expense.is_active = False
    expense.save()
    return Expense.objects.create(
        family=expense.family,
        created_by=user,
        description=data.get("description"),
        expense_type=data.get(
            "expense_type",
            expense.expense_type
        ),
        amount=data.get("amount"),
        expense_date=data.get("expense_date"),
        parent_a_share=data.get(
            "parent_a_share",
            expense.parent_a_share
        ),
        parent_b_share=data.get(
            "parent_b_share",
            expense.parent_b_share
        ),
        previous_version=expense,
        version=expense.version + 1
    )


def approve_expense(expense, role):
    if role == "parent_a" and expense.approved_by_parent_a is not True:
        expense.approved_by_parent_a = True

    elif role == "parent_b" and expense.approved_by_parent_b is not True:
        expense.approved_by_parent_b = True

    expense.save()
    return expense
