from expenses.models import Expense


def create_expense(family, user, data):
    return Expense.objects.create(
        family=family,
        created_by=user,
        description=data.get("description"),
        expense_type=data.get("expense_type", "other"),
        amount=data.get("amount"),
        expense_date=data.get("expense_date"),

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

        previous_version=expense,
        version=expense.version + 1
    )



