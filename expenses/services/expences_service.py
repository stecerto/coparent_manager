# expenses/services/expenses_service.py
from django.utils import timezone
from decimal import Decimal

from expenses.models import Expense
from notifications.services import create_notification
from django.db.models import Sum, Q
from datetime import date
from children.models import ChildSupport

from django.db.models import Sum, Q
from datetime import date
from children.models import ChildSupport
from expenses.models import Expense
from families.models import FamilyMember


def calculate_monthly_net_balance(child, month=None, year=None):
    """
    Calcola il saldo netto mensile tra i genitori per un figlio.
    Versione robusta con query semplificata per evitare falsi negativi.
    """
    if month is None:
        month = date.today().month
    if year is None:
        year = date.today().year

    # 1. MANTENIMENTO BASE (Query semplificata e più affidabile)
    # Prende l'ultimo supporto attivo per questo figlio, senza filtri date rigidi che potrebbero escluderlo
    current_support = child.supports.filter(
        support_type='child',
        is_active=True
    ).order_by('-start_date').first()

    maintenance_amount = float(current_support.amount) if current_support else 0.0
    payer_role = current_support.payer_role if current_support else 'parent_a'

    # 2. PERCENTUALI DI RIPARTIZIONE
    split_a = float(child.effective_split_pct_parent_a or 50.0)
    split_b = 100.0 - split_a

    # 3. SPESE STRAORDINARIE APPROVATE DEL MESE
    extra_expenses = Expense.objects.filter(
        child=child,
        is_active=True,
        status__in=['accepted', 'paid'],
        group_snapshot='straordinarie',
        expense_date__month=month,
        expense_date__year=year
    )

    extra_total = float(extra_expenses.aggregate(total=Sum('amount'))['total'] or 0.0)

    # Quote teoriche delle spese straordinarie
    quota_a = extra_total * (split_a / 100.0)
    quota_b = extra_total * (split_b / 100.0)

    # 4. CHI HA PAGATO MATERIALMENTE? (created_by)
    paid_by_a = 0.0
    paid_by_b = 0.0

    for exp in extra_expenses:
        exp_amount = float(exp.amount)

        # Determina il ruolo di chi ha creato la spesa
        creator_membership = FamilyMember.objects.filter(
            family=child.family,
            user=exp.created_by
        ).first()

        if creator_membership:
            if creator_membership.role == 'parent_a':
                paid_by_a += exp_amount
            elif creator_membership.role == 'parent_b':
                paid_by_b += exp_amount
        else:
            # Fallback sicuro se non troviamo il ruolo
            paid_by_a += exp_amount * (split_a / 100.0)
            paid_by_b += exp_amount * (split_b / 100.0)

    # 5. CALCOLO SALDO NETTO
    if payer_role == 'parent_a':
        # Genitore A versa a Genitore B
        net_balance = maintenance_amount + (quota_b - paid_by_a)
        payer = "Genitore A"
        receiver = "Genitore B"
    else:
        # Genitore B versa a Genitore A
        net_balance = maintenance_amount + (quota_a - paid_by_b)
        payer = "Genitore B"
        receiver = "Genitore A"

    # ✅ FIX UNBOUND LOCAL ERROR: Inizializziamo message e copriamo TUTTI i casi con tolleranza decimale
    message = "Calcolo in corso..."

    # Usiamo 0.01 come soglia per evitare problemi di arrotondamento floating point (es. 0.0000001)
    if net_balance <= 0.01:
        payer = "Nessuno"
        receiver = "Nessuno"
        net_balance = 0.0

        if maintenance_amount == 0.0 and extra_total == 0.0:
            message = "Nessun mantenimento configurato e nessuna spesa straordinaria approvata."
        elif extra_total == 0.0:
            message = "Nessuna spesa straordinaria approvata questo mese (in attesa di approvazione)."
        else:
            message = "Le quote sono compensate o la spesa è interamente a carico di chi l'ha anticipata."
    else:
        message = f"{payer} deve versare {receiver}: € {round(net_balance, 2)}"

    # 6. RESTITUZIONE DATI
    return {
        "maintenance": round(maintenance_amount, 2),
        "payer_role": payer_role,
        "extra_expenses_total": round(extra_total, 2),
        "quota_a": round(quota_a, 2),
        "quota_b": round(quota_b, 2),
        "paid_by_a": round(paid_by_a, 2),
        "paid_by_b": round(paid_by_b, 2),
        "net_balance": round(net_balance, 2),
        "payer": payer,
        "receiver": receiver,
        "message": message  # ✅ Ora è sempre associato a un valore
    }

def _get_effective_split_pct(child, override_pct=None):
    """Priorità: 1. Override manuale → 2. % profilo figlio → 3. 50%"""
    if override_pct is not None and override_pct > Decimal("0"):
        return override_pct
    if child and getattr(child, 'contribution_pct_parent_a', None) is not None:
        return child.contribution_pct_parent_a
    return Decimal("50.00")


def create_expense(family, user, child, expense_type, amount, description, expense_date, membership):
    if not expense_type:
        raise ValueError("expense_type obbligatorio")

    pct_a = _get_effective_split_pct(child, None)

    # ✅ LOGICA WORKFLOW DIVERSA IN BASE AL GRUPPO
    group_label = expense_type.group.label

    if group_label == "straordinarie":
        # ✅ Straordinarie semplici: stato "accepted" immediato (no approvazione)
        status = "accepted"
    elif group_label == "straordinarie_concordare":
        # ✅ Straordinarie da concordare: stato "pending" (richiede approvazione)
        status = "pending"
    else:
        # ✅ Ordinarie o altri: stato "pending" (default)
        status = "pending"

    return Expense.objects.create(
        family=family,
        created_by=user,
        modified_by=user,

        child=child,
        expense_type=expense_type,

        amount=amount,
        description=description,
        expense_date=expense_date,

        status=status,  # ✅ Stato dinamico

        effective_split_pct_a=pct_a,

        category_name_snapshot=expense_type.display_name,
        category_color_snapshot=expense_type.color,
        group_snapshot=group_label,

        version=1,
        previous_version=None,
        is_active=True,
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
    expense_type = model_data.get("expense_type")


    # ✅ Forza stato pending per la nuova versione (va riapprovata)
    model_data.pop("status", None)

    new_expense = Expense.objects.create(
        created_by=original.created_by,
        modified_by=user,
        effective_split_pct_a=pct_a,
        category_name_snapshot=expense_type.display_name,
        category_color_snapshot=expense_type.color,
        group_snapshot=expense_type.group.label,
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