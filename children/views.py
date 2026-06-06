import json
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from children.forms import ChildForm
from children.models import ChildProfile
from children.services.child_service import (
    create_child,
    update_child,
    archive_child
)
# children/views.py
from children.utils import calculate_expense_shares, get_child_split_pct
from expenses.models import Expense
from families.utils import get_family_of_user
from .forms import ChildSupportForm
from .notifications.services_notification import notify_other_parent
from .services.child_service import update_child_support


# children/views.py
# ... altri import ...

@login_required
def children_list(request):
    family = get_family_of_user(request.user, request=request)
    if not family:
        return render(request, "children/children_list.html", {"children": []})

    today = date.today()
    # ✅ Prefetcha relazioni per evitare query N+1
    children = list(family.children.filter(is_active=True).prefetch_related('supports', 'expenses'))

    for child in children:
        expenses_qs = Expense.objects.filter(child=child, is_active=True, status="accepted")
        # 💰 Mantenimento
        child.current_support = child.effective_maintenance_amount

        # 📊 Quote di ripartizione (fallback a 50/50 se mancante)
        pct_a = float(child.contribution_pct_parent_a or 50.0)
        if pct_a > 100: pct_a = 50.0
        pct_b = 100.0 - pct_a
        child.split_pct_a = round(pct_a, 2)
        child.split_pct_b = round(pct_b, 2)

        # 💵 Calcolo spese approvate
        approved_total = 0.0
        active_total = 0.0
        parent_a_total = 0.0
        parent_b_total = 0.0

        for exp in child.expenses.filter(is_active=True):
            # Ignora versioni archiviate
            if exp.previous_version_id is not None:
                continue  #salta versioni archiviate

            # ✅ È approvata se ENTRAMBI i genitori hanno User assegnato
            amount = float(exp.amount or 0)
            is_approved = bool(exp.approved_by_parent_a) and bool(exp.approved_by_parent_b)
            if is_approved:
                approved_total += amount
                # ✅ FIX SICURO: evita crash se la utility torna None
                shares = calculate_expense_shares(child, amount)
                if shares is None:
                    quota_a, quota_b = 0.0, 0.0
                else:
                    quota_a, quota_b = shares
                parent_a_total += quota_a
                parent_b_total += quota_b
            else:
                active_total += amount

        # ✅ Assegna al child per il template
        child.approved_total = round(approved_total, 2)
        child.active_total = round(active_total, 2)
        child.parent_a_total = round(parent_a_total, 2)
        child.parent_b_total = round(parent_b_total, 2)
        child.maintenance_balance = round(child.parent_a_total - child.parent_b_total, 2)


        # 📐 SALDO CHIARO: differenza tra quote.
        # Se > 0 → La quota di A è maggiore (B deve rimborsare A se ha pagato A)
        # ✅ Percentuali per il template (se vuoi mostrarle)
        child.split_pct_a = get_child_split_pct(child)
        child.split_pct_b = 100.0 - child.split_pct_a

    return render(request, "children/children_list.html", {"children": children})

@login_required
def child_detail(request, child_id):
    child = get_object_or_404(ChildProfile, id=child_id, is_active=True)

    today = date.today()

    # 👉 mantenimento attuale
    current_support = child.supports.filter(
        start_date__lte=today
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    ).order_by("-start_date").first()

    # 👉 storico
    supports_history = child.supports.all().order_by("-start_date")

    support_data = [
        {
            "date": str(s.start_date),
            "amount": float(s.amount)
        }
        for s in supports_history
    ]

    return render(request, "children/child_detail.html", {
        "child": child,
        "current_support": current_support,
        "supports_history": supports_history,
        "support_data": json.dumps(support_data)
    })
from django.db import transaction
# children/views.py
from decimal import Decimal
from django.utils import timezone
from datetime import date
from django.db import transaction

@login_required
def child_create_view(request):
    family = get_family_of_user(request.user, request=request)
    if not family:
        messages.error(request, "⚠️ Nessuna famiglia associata.")
        return redirect("families:setup")

    if request.method == "POST":
        form = ChildForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                child = create_child(family, request.user, form.cleaned_data)

                # ✅ FIX: Gestione sicura di amt (evita TypeError o crash su None)
                amt = form.cleaned_data.get("manual_maintenance_amount")
                if amt is not None:
                    try:
                        amt_decimal = Decimal(str(amt))
                        if amt_decimal > Decimal("0"):
                            update_child_support(child, amt_decimal, date.today())
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"⚠️ Salto mantenimento per errore conversione: {e}")

            messages.success(request, f"✅ {child.name} aggiunto correttamente.")
            return redirect("children:children_list")
    else:
        form = ChildForm()

    return render(request, "children/child_form.html", {"form": form, "family": family})


# children/views.py
@login_required
def child_update_view(request, pk):
    child_id = pk
    family = get_family_of_user(request.user, request=request)
    child = get_object_or_404(ChildProfile, id=child_id, family=family, is_active=True)

    # ✅ Salva valore PRE-modifica per storico
    old_pct = child.contribution_pct_parent_a

    if request.method == "POST":
        form = ChildForm(request.POST, instance=child)
        if form.is_valid():
            # ✅ update_child DEVE restituire l'istanza aggiornata
            updated = update_child(child, request.user, form.cleaned_data)
            if updated is None:
                child.refresh_from_db()
                updated = child

            # 📜 REGISTRA MODIFICA RIPARTIZIONE (se cambiata)
            new_pct = form.cleaned_data.get("contribution_pct_parent_a")
            if old_pct != new_pct:
                from .models import ChildSplitHistory
                ChildSplitHistory.objects.create(
                    child=updated, old_pct=old_pct, new_pct=new_pct,
                    changed_by=request.user, changed_at=timezone.now()
                )
                messages.info(request, f"📊 Ripartizione aggiornata: {old_pct}% → {new_pct}%")

            # 💰 Aggiorna mantenimento se modificato
            amt = form.cleaned_data.get("manual_maintenance_amount")
            if amt is not None and amt > Decimal("0"):
                update_child_support(updated, amt, date.today())

            messages.success(request, f"✅ Dati di {updated.name} aggiornati (v{updated.version})")
            return redirect("children:children_list")
        else:
            messages.error(request, "⚠️ Correggi gli errori evidenziati")
    else:
        form = ChildForm(instance=child)
        active_amt = child.effective_maintenance_amount
        if active_amt:
            form.initial["manual_maintenance_amount"] = active_amt

    return render(request, "children/child_form.html", {"form": form, "child": child})


@login_required
def update_support(request, child_id):
    child = get_object_or_404(ChildProfile, id=child_id, is_active=True)
    form = ChildSupportForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        new_support = update_child_support(
            child=child,
            new_amount=form.cleaned_data["amount"],
            start_date=form.cleaned_data["start_date"]
        )
        messages.success(request, f"💰 Mantenimento aggiornato a {new_support.amount} €")
        notify_other_parent(
            child,
            f"Mantenimento aggiornato a {new_support.amount} €",
            request.user
        )

        # ✅ Namespace corretto per il redirect
        return redirect("children:child_detail", child_id=child.id)

    return render(request, "children/update_support.html", {"form": form, "child": child})


@login_required
def child_delete_view(request, pk):
    child = get_object_or_404(ChildProfile, pk=pk)

   # archive_child(child, request.user)

    if request.method =='POST':
        archive_child(child, request.user)
        messages.success(request, "🗑️ Figlio archiviato correttamente")
        return redirect("children:children_list")

    return render(request,"children/child_confirm_delete.html", {"child": child})


def export_child_pdf(request, child_id):
    child = get_object_or_404(ChildProfile, id=child_id)

    supports = child.supports.all().order_by("-start_date")
    # ✅ Usa contesto con 'with' per sicurezza file system
    from .services.pdf_service import generate_child_report
    file_path = generate_child_report(child, supports)

    return FileResponse(open(file_path, "rb"), as_attachment=True, filename=f"report_{child.name}.pdf")

# children/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from families.utils import get_family_of_user
from .models import ChildProfile
from children.utils import generate_child_report_pdf

# children/views.py
@login_required
def child_pdf_view(request, child_id):
    family = get_family_of_user(request.user, request=request)
    child = get_object_or_404(ChildProfile, id=child_id, family=family, is_active=True)

    # ✅ Calcola esplicitamente il mantenimento attivo
    current_support = child.effective_maintenance_amount

    expenses_qs = child.expenses.filter(is_active=True, status='accepted').select_related('expense_type').order_by('-expense_date')

    pct_a = float(child.contribution_pct_parent_a or 50.0)
    pct_b = 100.0 - pct_a

    approved_total = 0.0
    parent_a_total = 0.0
    parent_b_total = 0.0
    expenses_data = []

    for exp in expenses_qs:
        amt = float(exp.amount or 0)
        qa = amt * (pct_a / 100)
        qb = amt * (pct_b / 100)
        approved_total += amt
        parent_a_total += qa
        parent_b_total += qb
        expenses_data.append({'exp': exp, 'quota_a': round(qa, 2), 'quota_b': round(qb, 2)})

    balance = round(parent_a_total - parent_b_total, 2)

    pdf_bytes = generate_child_report_pdf(
        child, current_support, expenses_data, approved_total,
        parent_a_total, parent_b_total, pct_a, pct_b, balance, request
    )

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="scheda_{child.name}_{child.surname}.pdf"'
    return response