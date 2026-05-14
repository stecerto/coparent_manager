# expenses/views.py
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.http import HttpResponseForbidden, FileResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from documents.models import Document
from families.utils import get_family_of_user
from families.models import FamilyMember
from expenses.forms import ExpenseForm
from .models import Expense, ExpenseCategory
from .pdf_utils import generate_expense_report  # ✅ Assicurati che il nome del file sia corretto
from expenses.services.expences_service import create_expense, update_expense, approve_expense
from .utils import get_expense_shares


@login_required
def expenses_dashboard(request):
    family = get_family_of_user(request.user)
    expenses = Expense.objects.filter(family=family, is_active=True).select_related(
        "child", "created_by", "expense_type"
    ).order_by("-expense_date")

    expenses, form, data, page_title = filter_expenses_with_metadata(request, expenses, family)

    total_expenses = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    parent_a_total = Decimal("0.00")
    parent_b_total = Decimal("0.00")
    for exp in expenses:
        if exp.child:
            a, b = get_expense_shares(exp)
            parent_a_total += a
            parent_b_total += b

    category_summary = expenses.values("expense_type_id", "expense_type__display_name", "expense_type__color").annotate(
        total=Sum("amount")
    ).order_by("expense_type__display_name")

    return render(request, "expenses/expenses_dashboard.html", {
        "expenses": expenses[:5],
        "total_expenses": total_expenses,
        "parent_a_total": parent_a_total,
        "parent_b_total": parent_b_total,
        "category_summary": category_summary,
        "page_title": page_title,
    })


@login_required
def expenses_list(request):
    family = get_family_of_user(request.user)
    expenses = Expense.objects.filter(family=family, is_active=True).select_related(
        "child", "created_by", "expense_type"
    ).order_by("-expense_date")  # ✅ Rimosso .order_by() duplicato

    expenses, form, data, page_title = filter_expenses_with_metadata(request, expenses, family)
    total_expenses = expenses.aggregate(total=Sum("amount"))["total"] or 0

    expenses_with_editable = []
    for exp in expenses:
        if exp.status in ("pending", "rejected"):
            exp.is_editable_flag = True
        elif exp.status == "paid":
            exp.is_editable_flag = False
        elif exp.status == "accepted":
            exp.is_editable_flag = not (exp.approved_by_parent_a or exp.approved_by_parent_b)
        else:
            exp.is_editable_flag = False
        expenses_with_editable.append(exp)

    return render(request, "expenses/expenses_list.html", {
        "expenses": expenses_with_editable,
        "form": form,
        "total_expenses": total_expenses,
        "page_title": page_title,
    })

from django.contrib import messages


@login_required
def add_expense(request):
    family = get_family_of_user(request.user)
    if not family:
        messages.error(request, "⚠️ Nessuna famiglia associata")
        return redirect("expenses:expenses_list")

    membership = family.members.filter(user=request.user).first()
    if not membership or membership.role not in ["parent_a", "parent_b"]:
        messages.error(request, "⚠️ Solo i genitori possono inserire spese")
        return redirect("expenses:expenses_list")

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            child = form.cleaned_data["child"]

            # ✅ Il service crea, salva e applica lo snapshot %
            expense = create_expense(family, request.user, form.cleaned_data, child, membership)

            # ✅ Il service imposta l'approvazione FK correttamente
            approve_expense(expense, request.user, membership.role)

            # 📎 Allegati
            for f in request.FILES.getlist('payment_proof'):
                Document.objects.create(
                    family=family, owner=request.user, uploaded_by=request.user,
                    expense=expense, file=f,
                    title=f"Prova_pagamento_v{expense.version}_{f.name[:50]}",
                    category="payment_proof", scope="shared", status="approved", is_active=True
                )

            messages.success(request, "✅ Spesa inserita (v1). In attesa dell'altro genitore.")
            return redirect("expenses:expenses_dashboard")
    else:
        form = ExpenseForm(user=request.user)

    return render(request, "expenses/expenses_form.html", {"form": form, "title": "Aggiungi Spesa"})


@login_required
def expense_update(request, pk):
    family = get_family_of_user(request.user)
    original_expense = get_object_or_404(Expense, pk=pk, family=family, is_active=True)

    if original_expense.created_by != request.user:
        return HttpResponseForbidden("Non puoi modificare questa spesa")

    membership = family.members.filter(user=request.user).first()
    if not membership or membership.role not in ["parent_a", "parent_b"]:
        messages.error(request, "⚠️ Solo i genitori possono modificare spese")
        return redirect("expenses:expenses_list")

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, instance=original_expense, user=request.user)
        if form.is_valid():
            child = form.cleaned_data["child"]

            # ✅ Il service: 1) archivia v corrente 2) crea v+1 salvata 3) applica snapshot %
            new_expense = update_expense(original_expense, request.user, form.cleaned_data, child, membership)

            # ✅ Auto-approva chi sta modificando
            approve_expense(new_expense, request.user, membership.role)

            # 📎 Allegati per la nuova versione
            for f in request.FILES.getlist('payment_proof'):
                Document.objects.create(
                    family=family, owner=request.user, uploaded_by=request.user,
                    expense=new_expense, file=f,
                    title=f"Prova_pagamento_v{new_expense.version}_{f.name[:50]}",
                    category="payment_proof", scope="shared", status="approved", is_active=True
                )

            messages.success(request, f"✅ Spesa aggiornata a v{new_expense.version}. In attesa di approvazione.")
            return redirect("expenses:expenses_list")
    else:
        form = ExpenseForm(instance=original_expense, user=request.user)

    return render(request, "expenses/expenses_form.html", {"form": form, "title": "Modifica Spesa"})


@login_required
def expense_history(request, pk):
    # ✅ Sicurezza: filtra per famiglia dell'utente (evita ID enumeration)
    expense = get_object_or_404(Expense, pk=pk, family=get_family_of_user(request.user))

    # Ricostruisci catena: versione corrente → previous → previous...
    versions = []
    curr = expense
    while curr:
        versions.append(curr)
        curr = curr.previous_version
    versions.reverse()  # Dalla più vecchia alla più recente

    return render(request, "expenses/expense_history.html", {
        "expense": expense,
        "expense_versions": versions
    })

@require_POST
@login_required
def update_expense_status(request):
    """AJAX: Aggiorna accepted/rejected dai pulsanti 🔵🔴"""
    import json
    try:
        data = json.loads(request.body)
        expense_id = data.get("expense_id")
        new_status = data.get("status")

        if new_status not in ["accepted", "rejected"]:
            return JsonResponse({"success": False, "error": "Stato non valido"}, status=400)

        expense = get_object_or_404(Expense, pk=expense_id, family=get_family_of_user(request.user))

        # 🚫 Sicurezza: solo il NON creatore può confermare
        if expense.created_by == request.user:
            return JsonResponse({"success": False, "error": "Solo l'altro genitore può approvare o rifiutare"},
                                status=403)

        if new_status == "accepted":
            approve_expense(expense, request.user, "parent_b")
            expense.status = "accepted"
        elif new_status == "rejected":
            approve_expense(expense, request.user, "parent_b")
            expense.status = "rejected"

        expense.save(update_fields=["status"])
        return JsonResponse({"success": True, "new_status": new_status})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_POST
@login_required
def upload_payment_proof(request):
    """AJAX: Upload ricevuta → transizione a paid"""
    try:
        expense_id = request.POST.get("expense_id")
        expense = get_object_or_404(Expense, pk=expense_id, family=get_family_of_user(request.user))

        # Sicurezza: solo il NON creatore può caricare la prova
        if expense.created_by == request.user:
            return JsonResponse({"success": False, "error": "Solo l'altro genitore può caricare la prova di pagamento"}, status=403)

        if expense.status == "paid":
            return JsonResponse({"success": False, "error": "Pagamento già completato"}, status=400)

        file = request.FILES.get("proof_file")
        if not file:
            return JsonResponse({"success": False, "error": "Nessun file ricevuto"}, status=400)

        # ✅ Crea il documento collegato alla spesa
        Document.objects.create(
            family=expense.family,
            owner=request.user,
            uploaded_by=request.user,
            expense=expense,
            file=file,
            title=f"Prova_pagamento_{expense.id}_{file.name[:50]}",
            category="payment_proof",
            scope="shared",
            status="approved",
            is_active=True
        )

        # ✅ AGGIORNA DIRETTAMENTE L'OGGETTO ESISTENTE (NO form.save())
        if not expense.approved_by_parent_b:
            approve_expense(expense, request.user, "parent_b")

        expense.status = "paid"
        expense.save(update_fields=["status"]) # ✅ Salvataggio esplicito

        return JsonResponse({
            "success": True,
            "new_status": expense.status,
            "payment_state": expense.payment_state
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# chat/views.py
@require_POST
@login_required
def send_rejection_message(request):
    """AJAX: Invia messaggio di giustificazione rifiuto in chat"""
    try:
        import json
        from expenses.models import Expense
        from chat.services.message_service import send_message

        data = json.loads(request.body)
        expense_id = data.get("expense_id")
        reason = data.get("reason", "").strip()
        notify = data.get("notify_sender", False)

        if not expense_id or not reason:
            return JsonResponse({"success": False, "error": "Dati mancanti"}, status=400)

        expense = Expense.objects.get(pk=expense_id, family=get_family_of_user(request.user))

        # Costruisci messaggio strutturato
        content = (
            f"🔴 *Rifiuto spesa*\n\n"
            f"📅 Data: {expense.expense_date.strftime('%d/%m/%Y')}\n"
            f"🏷️ Categoria: {expense.expense_type.display_name if expense.expense_type else 'N/D'}\n"
            f"💰 Importo: € {expense.amount}\n"
            f"👤 Inserita da: {expense.created_by.display_name}\n\n"
            f"❌ Motivazione: {reason}"
        )

        # Invia in chat familiare
        message = send_message(
            family=expense.family,
            sender=request.user,
            content=content,
            reply_to=None
        )

        # Notifica email opzionale al creatore
        if notify and expense.created_by != request.user:
            from django.core.mail import send_mail
            from django.conf import settings
            send_mail(
                subject=f"🔴 Spesa rifiutata: {expense.expense_type}",
                message=f"{request.user.display_name} ha rifiutato la tua spesa.\n\nMotivo:\n{reason}\n\nVedi la chat per dettagli: {request.build_absolute_uri('/chat/')}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[expense.created_by.email],
                fail_silently=True
            )

        return JsonResponse({
            "success": True,
            "message_id": message.id,
            "chat_url": f"/chat/"
        })

    except Expense.DoesNotExist:
        return JsonResponse({"success": False, "error": "Spesa non trovata"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def expense_delete(request, pk):
    family = get_family_of_user(request.user)
    expense = get_object_or_404(Expense, pk=pk, family=family)
    if expense.created_by != request.user:
        return HttpResponseForbidden("Non puoi eliminare questa spesa")

    if request.method == "POST":
        expense.is_active = False
        expense.save()
        return redirect("expenses:expenses_list")
    return render(request, "expenses/expenses_confirm_delete.html", {"expense": expense})


@login_required
def download_expense_pdf(request):
    pdf_buffer = generate_expense_report(request.user)
    return FileResponse(pdf_buffer, as_attachment=True, filename="report_spese.pdf")


@login_required
def expenses_calendar(request):
    family = get_family_of_user(request.user)
    expenses = Expense.objects.filter(family=family, is_active=True)
    data = []
    for e in expenses:
        data.append({
            "id": e.id,
            "title": f"{e.amount} €",
            "start": str(e.expense_date),
            "allDay": True,
            "extendedProps": {
                "status": e.status,
                "type": e.expense_type.display_name if e.expense_type else None,
                "color": e.expense_type.color if e.expense_type else None,
            }
        })
    return JsonResponse(data, safe=False)


@login_required
def expense_day_detail(request, date):
    family = get_family_of_user(request.user)
    expenses = Expense.objects.filter(family=family, expense_date=date, is_active=True).select_related("child",
                                                                                                       "created_by")
    return render(request, "expenses/day_detail.html", {"expenses": expenses, "date": date})


@login_required
def expenses_riepilogo_spese(request):
    family = get_family_of_user(request.user)


# ========================================================================
# UTILS (Sposta in un file utils.py se preferisci)
# ========================================================================
def filter_expenses_with_metadata(request, queryset, family):
    from .forms import ExpenseFilterForm
    form = ExpenseFilterForm(request.GET or None, family=family)
    data = {}
    title_parts = []

    if form.is_valid():
        data = form.cleaned_data

        if data.get("child"):
            queryset = queryset.filter(child=data["child"])
            title_parts.append(str(data["child"]))

        if data.get("status"):
            queryset = queryset.filter(status=data["status"])
            label = dict(Expense.STATUS_CHOICES).get(data["status"])
            if label: title_parts.append(label)

        if data.get("expense_type"):
            queryset = queryset.filter(expense_type=data["expense_type"])
            label = data["expense_type"].display_name  # ✅ CORRETTO
            if label: title_parts.insert(0, f"Spese filtrate per: {label.lower()}")

        if data.get("date_from"):
            queryset = queryset.filter(expense_date__gte=data["date_from"])
        if data.get("date_to"):
            queryset = queryset.filter(expense_date__lte=data["date_to"])

        date_from, date_to = data.get("date_from"), data.get("date_to")
        if date_from and date_to:
            title_parts.append(f"dal {date_from.strftime('%d.%m.%Y')} al {date_to.strftime('%d.%m.%Y')}")
        elif date_from:
            title_parts.append(f"dal {date_from.strftime('%d.%m.%Y')}")
        elif date_to:
            title_parts.append(f"fino al {date_to.strftime('%d.%m.%Y')}")

    page_title = "Spese filtrate per: " + " - ".join(
        p.capitalize() for p in title_parts) if title_parts else "Tutte le spese"

    return queryset, form, data, page_title


# Esempio in una view o service
def calculate_parent_debt(expense_amount, child):
    pct_a = float(child.contribution_pct_parent_a) / 100
    pct_b = 1.0 - pct_a

    amount_a = expense_amount * pct_a
    amount_b = expense_amount * pct_b
    return amount_a, amount_b