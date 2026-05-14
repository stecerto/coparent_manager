# expenses/services/expenses_service.py
from django.utils import timezone
from decimal import Decimal

from expenses.models import Expense


def _get_effective_split_pct(child, override_pct=None):
    """Priorità: 1. Override manuale → 2. % profilo figlio → 3. 50%"""
    if override_pct is not None and override_pct > Decimal("0"):
        return override_pct
    if child and getattr(child, 'contribution_pct_parent_a', None) is not None:
        return child.contribution_pct_parent_a
    return Decimal("50.00")


def create_expense(family, user, data, child, membership):
    """Crea spesa v1 con snapshot percentuale"""
    pct_a = _get_effective_split_pct(child, data.get("split_override_pct"))

    # ✅ Prepara i dati puliti (esclude split_override_pct)
    model_data = {k: v for k, v in data.items() if k not in ["split_override_pct"]}
    model_data["family"] = family
    model_data["child"] = child

    return Expense.objects.create(
        created_by=user,
        modified_by=user,
        effective_split_pct_a=pct_a,
        is_active=True,
        version=1,
        previous_version=None,
        **model_data
    )


def update_expense(original, user, data, child, membership):
    """Archivia versione corrente e crea v+1 con reset stato"""
    # 1. Archivia versione attiva
    original.is_active = False
    original.archived_at = timezone.now()
    original.save(update_fields=["is_active", "archived_at"])

    # 2. Calcola nuova percentuale
    pct_a = _get_effective_split_pct(child, data.get("split_override_pct"))

    # 3. Clona e aggiorna
    model_data = {k: v for k, v in data.items() if k not in ["split_override_pct"]}
    model_data["family"] = original.family
    model_data["child"] = child or original.child

    # ✅ Forza stato pending per la nuova versione (va riapprovata)
    model_data.pop("status", None)

    new_expense = Expense.objects.create(
        created_by=original.created_by,
        modified_by=user,
        effective_split_pct_a=pct_a,
        version=original.version + 1,
        previous_version=original,
        is_active=True,
        status="pending",
        **model_data
    )
    return new_expense


def approve_expense(expense, user, role):
    """
    ✅ CORRETTO: Il modello usa ForeignKey, quindi assegna l'istanza User.
    Prima: expense.approved_by_parent_a = True  → ❌ ValueError
    Ora:   expense.approved_by_parent_a = user  → ✅ OK
    """
    updated_fields = []
    if role == "parent_a" and expense.approved_by_parent_a != user:
        expense.approved_by_parent_a = user
        updated_fields.append("approved_by_parent_a")
    elif role == "parent_b" and expense.approved_by_parent_b != user:
        expense.approved_by_parent_b = user
        updated_fields.append("approved_by_parent_b")

    if updated_fields:
        expense.save(update_fields=updated_fields)
    return expense