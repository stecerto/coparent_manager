import json
from datetime import date

from django.http import FileResponse

from .notifications.services_notification import notify_other_parent
from .services.pdf_service import generate_child_report
from django.contrib import messages
from django.db.models import ExpressionWrapper, Sum, Q, Prefetch
from django.shortcuts import render
from .forms import ChildSupportForm
from .services.child_service import update_child_support
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from children.forms import ChildForm
from children.models import ChildProfile, ChildSupport
from children.services.child_service import (
    create_child,
    update_child,
    archive_child
)
from expenses.models import Expense
from families.utils import get_family_of_user


@login_required
def children_list(request):
    family = get_family_of_user(request.user)

    if not family:
        return render(request, "children/children_list.html", {"children": []})

    # ✅ solo spese valide
    valid_expenses = Expense.objects.filter(
        is_active=True,
        previous_version__isnull=True
    )

    # ✅ FILTRO CORRETTO PER FAMIGLIA
    children = family.children.filter(is_active=True).prefetch_related(
        Prefetch("expenses", queryset=valid_expenses)
    ).annotate(

        # 💰 SPESE APPROVATE
        approved_total=Sum(
            "expenses__amount",
            filter=Q(
                expenses__approved_by_parent_a=True,
                expenses__approved_by_parent_b=True
            )
        ),

        # 🔄 SPESE ATTIVE
        active_total=Sum(
            "expenses__amount",
            filter=~Q(
                expenses__approved_by_parent_a=True,
                expenses__approved_by_parent_b=True
            )
        ),

        # 👨 quota parent A
        parent_a_total=Sum(
            ExpressionWrapper(
                F("expenses__amount") * F("expenses__parent_a_share") / 100,
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
            filter=Q(
                expenses__approved_by_parent_a=True,
                expenses__approved_by_parent_b=True
            )
        ),

        # 👩 quota parent B
        parent_b_total=Sum(
            ExpressionWrapper(
                F("expenses__amount") * F("expenses__parent_b_share") / 100,
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
            filter=Q(
                expenses__approved_by_parent_a=True,
                expenses__approved_by_parent_b=True
            )
        ),
    )

    # 📅 oggi
    today = date.today()

    # 🔥 aggiungiamo mantenimento + saldo
    for child in children:

        # 👉 mantenimento attuale
        support = child.supports.filter(
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).order_by("-start_date").first()

        child.current_support = support.amount if support else None

        # 👉 saldo spese
        a = child.parent_a_total or 0
        b = child.parent_b_total or 0
        child.maintenance_balance = a - b

    return render(
        request,
        "children/children_list.html",
        {"children": children}
    )

@login_required
def child_detail(request, child_id):
    child = get_object_or_404(ChildProfile, id=child_id)

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

@login_required
def child_create_view(request):
    family = get_family_of_user(request.user)

    if not family:
        return redirect("setup")

    if request.method == "POST":
        form = ChildForm(request.POST)

        if form.is_valid():
            create_child(
                family,
                request.user,
                form.cleaned_data
            )
            return redirect("children:children_list")

    else:
        form = ChildForm()

    return render(
        request,
        "children/child_form.html",
        {"form": form}
    )


@login_required
def child_update_view(request, pk):
    child = get_object_or_404(
        ChildProfile,
        pk=pk,
        is_active=True
    )

    if request.method == "POST":
        form = ChildForm(
            request.POST,
            instance=child
        )

        if form.is_valid():
            update_child(
                child,
                request.user,
                form.cleaned_data
            )
            return redirect("children:children_list")

    else:
        form = ChildForm(instance=child)

    return render(
        request,
        "children/child_form.html",
        {"form": form}
    )




def update_support(request, child_id):
    child = get_object_or_404(ChildProfile, id=child_id)

    form = ChildSupportForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        new_support = update_child_support(
            child=child,
            new_amount=form.cleaned_data["amount"],
            start_date=form.cleaned_data["start_date"]
        )

        # 🚨 ALERT
        messages.success(
            request,
            f"Mantenimento aggiornato a {new_support.amount} €"
        )

        notify_other_parent(
            child,
            f"Mantenimento aggiornato a {new_support.amount} €",
            request.user
        )
        return redirect("child_detail", child_id=child.id)

    return render(request, "children/update_support.html", {
        "form": form,
        "child": child
    })

@login_required
def child_delete_view(request, pk):
    child = get_object_or_404(ChildProfile, pk=pk)

   # archive_child(child, request.user)

    if request.method =='POST':
        archive_child(child, request.user)
        return redirect("children:children_list")

    return render(request,"children/child_confirm_delete.html", {"child": child})


from django.http import FileResponse
from .services.pdf_service import generate_child_report


def export_child_pdf(request, child_id):
    child = get_object_or_404(ChildProfile, id=child_id)

    supports = child.supports.all().order_by("-start_date")

    file_path = generate_child_report(child, supports)

    return FileResponse(open(file_path, "rb"), as_attachment=True)