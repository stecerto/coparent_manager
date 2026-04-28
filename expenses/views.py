# expenses/views.py

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db.models.functions import Lower, Trim
from accounts.decorators import first_login_required, confirmed_required
from expenses.forms import ExpenseForm, ExpenseFilterForm
from expenses.models import Expense
from expenses.pdf_utils import generate_expense_report
from families.utils import get_family_of_user

def filter_expenses_with_metadata(request, queryset, family):
    family = get_family_of_user(request.user)
    form = ExpenseFilterForm(request.GET or None, family=family)
    data = {}
    title_parts = []

    if form.is_valid():
        data = form.cleaned_data

        # 🔍 FILTRI
        if data.get("child"):
            queryset = queryset.filter(child=data["child"])
            title_parts.append(str(data["child"]))

        if data.get("status"):
            queryset = queryset.filter(status=data["status"])
            status_label = dict(Expense.STATUS_CHOICES).get(data["status"])
            if status_label:
                title_parts.append(status_label)

        if data.get("expense_type"):
            queryset = queryset.filter(expense_type=data["expense_type"])
            type_label = dict(Expense.EXPENSE_TYPES).get(data["expense_type"])
            if type_label:
                title_parts.insert(0, f"Spese filtrate per: {type_label.lower()}")

        if data.get("date_from"):
            queryset = queryset.filter(expense_date__gte=data["date_from"])

        if data.get("date_to"):
            queryset = queryset.filter(expense_date__lte=data["date_to"])

        # 📅 DATE (costruzione titolo)
        date_from = data.get("date_from")
        date_to = data.get("date_to")

        if date_from and date_to:
            title_parts.append(
                f"dal {date_from.strftime('%d.%m.%Y')} al {date_to.strftime('%d.%m.%Y')}"
            )
        elif date_from:
            title_parts.append(
                f"dal {date_from.strftime('%d.%m.%Y')}"
            )
        elif date_to:
            title_parts.append(
                f"fino al {date_to.strftime('%d.%m.%Y')}"
            )

    # 🧠 TITOLO FINALE
    if title_parts:
        page_title = "Spese filtrate per: " + " - ".join(part.capitalize() for part in title_parts)

    else:
        page_title = "Tutte le spese"

    return queryset, form, data, page_title


@login_required
@first_login_required
def expenses_dashboard(request):
    family = get_family_of_user(request.user)
    # 🔍 Query base
    expenses = Expense.objects.filter(
        family=family,
        is_active=True
    ).select_related("child", "created_by", "expense_type").order_by("-expense_date")

    # 🔧 FILTRI + TITOLO UNIFICATO
    expenses, form, data, page_title = filter_expenses_with_metadata(request,expenses,family)
    # 💰 TOTALE spese
    total_expenses = expenses.aggregate(
        total=Sum("amount")
    )["total"] or 0

    # 👨‍👩‍👧 SPLIT GENITORI
    parent_totals = expenses.aggregate(
        parent_a=Sum(
            ExpressionWrapper(
                F("amount") * F("parent_a_share") / 100,
                output_field=DecimalField()
            )
        ),
        parent_b=Sum(
            ExpressionWrapper(
                F("amount") * F("parent_b_share") / 100,
                output_field=DecimalField()
            )
        )
    )

    # 📊 CATEGORIE
    category_summary = (
        expenses
        .values("expense_type_id","expense_type__name", "expense_type__color")
        .annotate(total=Sum("amount"))
        .order_by("expense_type__name")
    )

    return render(request, "expenses/expenses_dashboard.html", {
        "expenses": expenses[:5],

        # KPI
        "total_expenses": total_expenses,
        "parent_a_total": parent_totals["parent_a"] or 0,
        "parent_b_total": parent_totals["parent_b"] or 0,
        "category_summary": category_summary,
        #UI
        "page_title": page_title,

    })



@login_required
def expenses_list(request):
    family = get_family_of_user(request.user)
    #query base
    expenses = Expense.objects.filter(
        family=family,
        is_active=True
    ).select_related("child", "created_by").order_by("-expense_date")
    #filtro + titolo unificato
    expenses, form, data, page_title = filter_expenses_with_metadata(
        request,
        expenses,
        family
    )
    # 💰 TOTALE (opzionale ma utile)
    total_expenses = expenses.aggregate(
        total=Sum("amount")
    )["total"] or 0


    return render(request, "expenses/expenses_list.html", {
        "expenses": expenses,
        "form": form,
        "total_expenses": total_expenses,
        "page_title": page_title,  # 🔥
    })


@login_required
@confirmed_required
@first_login_required
def expenses_riepilogo_spese(request):
    return render(request, "expenses/expenses_riepilogo_spese.html")




@login_required
def add_expense(request):
    family = get_family_of_user(request.user)

    if not family:
        return redirect("setup")

    if request.method == "POST":
        form = ExpenseForm(
            request.POST,
            user=request.user
        )

        if form.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.family = family
            expense.save()

            return redirect("expenses:expenses_dashboard")

    else:
        form = ExpenseForm(user=request.user)

    return render(
        request,
        "expenses/expenses_form.html",
        {
            "form": form,
            "title": "Aggiungi Spesa"
        }
    )


@login_required
def expense_update(request, pk):
    family = get_family_of_user(request.user)

    expense = get_object_or_404(
        Expense,
        pk=pk,
        family=family,
        is_active=True
    )
    if expense.created_by != request.user:
        return HttpResponseForbidden("Non puoi modificare questa spesa")

    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense, user=request.user)

        if form.is_valid():
            form.save()
            return redirect("expenses:expenses_list")

    else:
        form = ExpenseForm(instance=expense, user=request.user)

    return render(
        request,
        "expenses/expenses_form.html",
        {
            "form": form,
            "title": "Modifica Spesa"
        }
    )

import json

'''
@login_required
def update_expense_status(request, pk):
    if request.method == "POST":
        data = json.loads(request.body)

        expense = get_object_or_404(Expense, pk=pk)

        expense.status = data.get("status")
        expense.save()

        return JsonResponse({"success": True})

    return JsonResponse({"success": False}, status=400)

'''
@require_POST
@login_required
def update_status(request, pk):
    expense = get_object_or_404(
        Expense,
        pk=pk,
        family=get_family_of_user(request.user)
    )

    data = json.loads(request.body)
    new_status = data.get("status")

    expense.status = new_status
    expense.save()

    return JsonResponse({"success": True})


@login_required
def expense_delete(request, pk):
    family = get_family_of_user(request.user)

    expense = get_object_or_404(
        Expense,
        pk=pk,
        family=family
    )
    if expense.created_by != request.user:
        return HttpResponseForbidden("Non puoi eliminare questa spesa")

    if request.method == "POST":
        expense.is_active = False
        expense.save()

        return redirect("expenses:expenses_list")

    return render(
        request,
        "expenses/expenses_confirm_delete.html",
        {"expense": expense}
    )


@login_required
def download_expense_pdf(request):
    pdf_buffer = generate_expense_report(request.user)

    return FileResponse(
        pdf_buffer,
        as_attachment=True,
        filename="report_spese.pdf"
    )

from django.http import JsonResponse

@login_required
def expenses_calendar(request):
    family = get_family_of_user(request.user)

    expenses = Expense.objects.filter(
        family=family,
        is_active=True
    )

    data = []

    for e in expenses:
        data.append({
            "id": e.id,
            "title": f"{e.amount} €",
            "start": str(e.expense_date),  # 🔥 sicuro anche senza isoformat
            "allDay": True,
            "extendedProps": {
                "status": e.status,
                "type": e.expense_type.name if e.expense_type else None,
                "color": e.expense_type.color if e.expense_type else None,
            }
        })

    return JsonResponse(data, safe=False)

@login_required
def expense_day_detail(request, date):
    family = get_family_of_user(request.user)

    expenses = Expense.objects.filter(
        family=family,
        expense_date=date,
        is_active=True
    ).select_related("child", "created_by")

    return render(request, "expenses/day_detail.html", {
        "expenses": expenses,
        "date": date
    })