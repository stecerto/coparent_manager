# expenses/views.py

import json

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from documents.models import Document
from accounts.decorators import first_login_required, confirmed_required
from expenses.forms import ExpenseForm, ExpenseFilterForm
from expenses.models import Expense

from expenses.pdf_utils import generate_expense_report
from families.utils import get_family_of_user

import json
from decimal import Decimal
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, FileResponse, JsonResponse
from documents.models import Document
from .models import Expense
from .forms import ExpenseForm
from families.utils import get_family_of_user
from .pdf_utils import generate_expense_report  # ✅ Assicurati che il nome del file sia corretto


@login_required
def expenses_dashboard(request):
    family = get_family_of_user(request.user)
    expenses = Expense.objects.filter(family=family, is_active=True).select_related(
        "child", "created_by", "expense_type"
    ).order_by("-expense_date")

    expenses, form, data, page_title = filter_expenses_with_metadata(request, expenses, family)

    total_expenses = expenses.aggregate(total=Sum("amount"))["total"] or 0
    parent_totals = expenses.aggregate(
        parent_a=Sum(ExpressionWrapper(F("amount") * F("parent_a_share") / 100, output_field=DecimalField())),
        parent_b=Sum(ExpressionWrapper(F("amount") * F("parent_b_share") / 100, output_field=DecimalField()))
    )
    category_summary = expenses.values("expense_type_id", "expense_type__display_name", "expense_type__color").annotate(
        total=Sum("amount")
    ).order_by("expense_type__display_name")

    return render(request, "expenses/expenses_dashboard.html", {
        "expenses": expenses[:5],
        "total_expenses": total_expenses,
        "parent_a_total": parent_totals["parent_a"] or 0,
        "parent_b_total": parent_totals["parent_b"] or 0,
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


@login_required
def add_expense(request):
    family = get_family_of_user(request.user)
    if not family:
        return redirect("setup")

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.family = family
            expense.save()

            for f in request.FILES.getlist('payment_proof'):
                Document.objects.create(
                    family=family, owner=request.user, uploaded_by=request.user,
                    expense=expense, file=f, title=f"Prova_pagamento_{expense.id}_{f.name[:50]}",
                    category="payment_proof", scope="shared", status="approved", is_active=True
                )
            return redirect("expenses:expenses_dashboard")
    else:
        form = ExpenseForm(user=request.user)

    return render(request, "expenses/expenses_form.html", {"form": form, "title": "Aggiungi Spesa"})


@login_required
def expense_update(request, pk):
    family = get_family_of_user(request.user)
    expense = get_object_or_404(Expense, pk=pk, family=family, is_active=True)

    if expense.created_by != request.user:
        return HttpResponseForbidden("Non puoi modificare questa spesa")

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, instance=expense, user=request.user)
        if form.is_valid():
            form.save()
            for f in request.FILES.getlist('payment_proof'):
                Document.objects.create(
                    family=family, owner=request.user, uploaded_by=request.user,
                    expense=expense, file=f, title=f"Prova_pagamento_{expense.id}_{f.name[:50]}",
                    category="payment_proof", scope="shared", status="approved",
                    modified_by=request.user, is_active=True
                )
            return redirect("expenses:expenses_list")
    else:
        form = ExpenseForm(instance=expense, user=request.user)

    return render(request, "expenses/expenses_form.html", {"form": form, "title": "Modifica Spesa"})


@require_POST
@login_required
def update_expense_status(request):
    """AJAX: Aggiorna accepted/rejected dai pulsanti 🔵🔴"""
    try:
        data = json.loads(request.body)
        expense_id = data.get("expense_id")
        new_status = data.get("status")

        if new_status not in ["accepted", "rejected"]:
            return JsonResponse({"success": False, "error": "Stato non valido"}, status=400)

        expense = get_object_or_404(Expense, pk=expense_id, family=get_family_of_user(request.user))
        if expense.created_by == request.user:
            return JsonResponse({"success": False, "error": "Solo l'altro genitore può approvare o rifiutare"},
                                status=403)

        expense.status = new_status
        expense.save()
        return JsonResponse({"success": True, "new_status": new_status})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_POST
@login_required
def upload_payment_proof(request):
    """AJAX: Upload ricevuta → transizione partial/paid"""
    try:
        expense_id = request.POST.get("expense_id")
        expense = get_object_or_404(Expense, pk=expense_id, family=get_family_of_user(request.user))

        if expense.payment_status == "paid":
            return JsonResponse({"success": False, "error": "Pagamento già completato"}, status=400)

        file = request.FILES.get("proof_file")
        if not file:
            return JsonResponse({"success": False, "error": "Nessun file ricevuto"}, status=400)

        Document.objects.create(
            family=expense.family, owner=request.user, uploaded_by=request.user,
            expense=expense, file=file, title=f"Prova_pagamento_{expense.id}_{file.name[:50]}",
            category="payment_proof", scope="shared", status="approved", is_active=True
        )

        if expense.payment_status in ["unpaid", None]:
            expense.payment_status = "partial"
        elif expense.payment_status == "partial":
            expense.payment_status = "paid"
            expense.status = "paid"
        expense.save()

        return JsonResponse({"success": True, "new_status": expense.status, "payment_state": expense.payment_status})
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
            label = dict(Expense.EXPENSE_TYPES).get(data["expense_type"])
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