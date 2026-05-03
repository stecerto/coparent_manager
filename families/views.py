import token
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from families.services.balance_service import calculate_family_balance

from django.db.models import Sum
from documents.models import AuditLog, Document
from expenses.models import Expense
from families.forms import InvitationForm
from families.models import FamilyMember, Invitation
from families.services.expense_service import create_expense
from families.services.invitation_service import create_invitation, send_invitation_email, accept_invitation, \
    generate_token, build_whatsapp_link
from families.utils import get_family_of_user, is_lawyer
from accounts.models import UserProfile
from families.services.setup_service import handle_setup
from django.contrib.auth.decorators import user_passes_test

from families.utils import is_parent
from calendar_app.services.calendar_service import get_family_events


@user_passes_test(is_lawyer)
def lawyer_dashboard(request):
    pass


@user_passes_test(is_parent)
def family_dashboard(request):
    pass


@login_required
def setup_view(request):
    result = handle_setup(request)
    redirect_url = result.get("redirect")
    if redirect_url:
        return redirect(redirect_url)

    return render(
        request,
        "families/setup.html",
        result.get("context", {})
    )


def invitation_landing_view(request, token):
    invitation = get_object_or_404(Invitation, token=token, status="pending")

    if invitation.is_expired:
        return render(request, "families/invite_expired.html")
    # salva token per login / registrazione
    request.session["pending_invite_token"] = str(token)
    # se utente già esiste → login
    existing_user = None

    if invitation.email:
        existing_user = User.objects.filter(
            email=invitation.email
        ).first()

    return render(request, "families/invitation_landing.html",
        {
            "invitation": invitation,
            "existing_user": existing_user
        })


def confirm_invitation_view(request, token):
    invitation = get_object_or_404(
        Invitation,
        token=token,
        status="pending"
    )

    if invitation.is_expired:
        return render(request, "families/invite_expired.html")

    # conferma esplicita
    request.session["pending_invite_token"] = str(token)

    return render(
        request,
        "families/invite_confirm.html",
        {
            "invitation": invitation
        }
    )

@login_required
def expense_list_view(request):
    family = get_family_of_user(request.user)
    if not family:
        return redirect("families:setup")

    expenses = (
        Expense.objects
        .filter(family=family, is_active=True)
        .select_related("created_by")
        .order_by("-expense_date")
    )

    return render(
        request,
        "families/expenses.html",
        {"expenses": expenses}
    )


@login_required
def create_expense_view(request):
    family = get_family_of_user(request.user)

    if not family:
        return redirect("families:setup")

    if request.method == "POST":
        expense = create_expense(
            family,
            request.user,
            request.POST
        )

        files = request.FILES.getlist("documents")

        for f in files:
            Document.objects.create(
                family=family,
                owner=request.user,
                uploaded_by=request.user,
                expense=expense,
                file=f,
                title=f.name,
                category="payment_proof",  # o "generic" se non hai aggiunto la choice
                scope="shared",
                status="approved",
                is_active=True
            )

        return redirect("families:expenses")

    return render(request, "families/create_expense.html")


@login_required
def approve_expense_view(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, is_active=True)

    membership = FamilyMember.objects.filter(
        user=request.user,
        family=expense.family
    ).first()

    if not membership:
        return redirect("families:family_dashboard")

    if membership.role == "parent_a":
        expense.approved_by_parent_a = True

    elif membership.role == "parent_b":
        expense.approved_by_parent_b = True

    expense.save()

    return redirect("families:expenses")


# _______________________________________________________________________________________
from families.services.email_service import (
    send_invitation_email,
    build_invitation_context
)


@login_required
@transaction.atomic
def invite_member_view(request):
    family = get_family_of_user(request.user)

    if not family:
        return redirect("families:setup")

    profile = request.user.userprofile

    form = InvitationForm(
        request.POST or None,
        user_role=profile.role
    )

    if request.method == "POST" and form.is_valid():

        display_name = form.cleaned_data.get("display_name")

        invitation = None

        with transaction.atomic():
            invitation = create_invitation(
                family=family,
                role=form.cleaned_data["role"],
                channel=form.cleaned_data["channel"],
                email=form.cleaned_data.get("email"),
                phone=form.cleaned_data.get("phone"),
                sender=request.user,
                expire_at=timezone.now() + timezone.timedelta(days=7),
                display_name=display_name
            )

        # 🔥 OUTSIDE TRANSACTION (IMPORTANT)
        if invitation.channel == "email":

            email_context = build_invitation_context(
                request,
                invitation,
                family
            )

            send_invitation_email(
                request,
                invitation,
                context_extra=email_context
            )

            return redirect("families:family_dashboard")

        if invitation.channel == "whatsapp":
            wa_link = build_whatsapp_link(request, invitation)
            return redirect(wa_link)

    return render(request, "families/invite_member.html", {
        "form": form
    })


# =========================
# ACCETTA INVITO
# =========================
def accept_invite_view(request, token):
    invitation = Invitation.objects.filter(
        token=token,
        status="pending"
    ).first()

    if not invitation:
        return render(
            request,
            "families/accept_invite/invite_invalid.html",
            {"reason": "invalid"}
        )

    if invitation.is_expired:
        invitation.mark_expired()
        return render(
            request,
            "families/accept_invite/invite_invalid.html",
            {"reason": "expired"}
        )

    request.session["invitation_id"] = invitation.id

    return redirect("accounts:register")

def register_member_after_signup(request, user):
    invitation_id = request.session.get("invitation_id")

    if not invitation_id:
        return

    invitation = Invitation.objects.filter(
        id=invitation_id,
        accepted=False,
        status="pending"
    ).first()

    if invitation:
        accept_invitation(invitation, user)

    request.session.pop("invitation_id", None)


@login_required
def resend_invitation_view(request, invitation_id):
    invitation = Invitation.objects.filter(
        id=invitation_id,
        family=get_family_of_user(request.user)
    ).first()

    if not invitation or invitation.status != "pending":
        return redirect("families:family_dashboard")

    profile = request.user.userprofile

    email_context = build_invitation_context(
        request,
        invitation,
        profile
    )

    send_invitation_email(
        request,
        invitation,
        template="emails/invitation_email.html",
        context_extra=email_context
    )

    invitation.increment_resend()

    return redirect("families:family_dashboard")


@login_required
def cancel_invitation_view(request, invitation_id):
    invitation = Invitation.objects.filter(id=invitation_id).first()

    if invitation and invitation.status == "pending":
        invitation.status = "cancelled"
        invitation.save()

    return redirect("families:family_dashboard")


@login_required
def dashboard_view(request):

    family = get_family_of_user(request.user)
    expenses = family.expenses.all().order_by("-expense_date")[:5]
    events = get_family_events(family)[:5]
    balance = calculate_family_balance(family)
    children = family.children.filter(is_active=True)
    total_expenses = sum(e.amount for e in expenses)

    context = {
        "family": family,
        "children": children,
        "expenses": expenses,
        "expenses_count": family.expenses.count(),
        "documents_count": family.documents.count(),
        "messages_count": family.chat.count() if hasattr(family, "chat") else 0,
        "events_count": family.calendar.count() if hasattr(family, "events") else 0,
        "children_count": family.children.count(),
        "balance": balance,
        "total_expenses": total_expenses,
    }

    return render(request, "families/family_dashboard.html", context)

    '''
    if not family:
        return redirect("families:setup")
    expenses = family.expenses.all().order_by("-expense_date")
    balance = calculate_family_balance(family)

    children = family.children.filter(is_active=True)
    total_expenses = sum(e.amount for e in expenses)

    context = {
        "family": family,
        "children": children,
        "expenses": expenses,
        "expenses_count": family.expenses.count(),
        "documents_count": family.documents.count(),
        "messages_count": family.chat.count() if hasattr(family, "chat") else 0,
        "events_count": family.calendar.count() if hasattr(family, "events") else 0,
        "children_count": family.children.count(),
        "balance": balance,
        "total_expenses": total_expenses,
    }

    return render(request, "families/family_dashboard.html", context)
'''


@login_required
def expenses_by_child(request):
    family = get_family_of_user(request.user)
    if not family:
        return JsonResponse({"error": "Nessuna famiglia"}, status=400)

    expenses = Expense.objects.filter(family=family, is_active=True)

    # Filtri opzionali
    if request.GET.get("child_id"):
        expenses = expenses.filter(child_id=request.GET["child_id"])
    if request.GET.get("category"):
        # ✅ Ora filtriamo per il nome visibile (quello che arriva dal grafico)
        expenses = expenses.filter(expense_type__display_name=request.GET["category"])

    # 📊 Dati per il grafico
    summary = (
        expenses
        .values("expense_type_id", "expense_type__display_name", "expense_type__color")  # ✅ MODIFICATO
        .annotate(total=Sum("amount"))
        .order_by("expense_type__display_name")
    )

    # 📋 Dati per la tabella
    expenses_list = list(expenses.values(
        "id",
        "expense_date",
        "amount",
        "expense_type__display_name",
        "expense_type__color",
        #"created_by__first_name",
        "created_by__email",
        "created_by__username",
        "status",
        "approved_by_parent_a",
        "approved_by_parent_b"
    ))

    # Formattazione sicura
    for exp in expenses_list:
        exp["expense_date"] = exp["expense_date"].strftime("%d/%m/%Y") if exp["expense_date"] else "-"
        if not exp.get("expense_type__display_name"):
            exp["expense_type__display_name"] = "N/D"
        status_labels = {
            "pending": "In Sospeso",
            "accepted": "Accettata",
            "paid": "Pagata",
            "rejected": "Rifiutata"
        }
        exp["status_display"] = status_labels.get(exp["status"], exp["status"])

        exp["created_by_display"] = (
                #exp.get("created_by__first_name") or
                exp.get("created_by__email") or
                exp.get("created_by__username") or
                "Utente"
        )

    data = {
        "labels": [s["expense_type__display_name"] or "N/D" for s in summary],
        "colors": [s["expense_type__color"] or "#6f42c1" for s in summary],
        "data": [float(s["total"] or 0) for s in summary],
        "expenses": expenses_list
    }

    return JsonResponse(data)

# =========================
# SUMMARY VIEW
# =========================
@login_required
def summary_view(request):
    profile = UserProfile.objects.get(user=request.user)

    family = get_family_of_user(request.user)

    children = family.children.filter(is_active=True) if family else []

    context = {
        "profile": profile,
        "family": family,
        "children": children,
    }

    return render(request, "families/summary.html", context)

@login_required
def family_timeline_view(request):
    family = get_family_of_user(request.user)

    logs = AuditLog.objects.filter(
        family=family
    ).select_related("user", "document").order_by("-created_at")

    return render(
        request,
        "families/timeline.html",
        {
            "family": family,
            "logs": logs
        }
    )

@login_required
def lawyer_dashboard_view(request):
    user = request.user

    logs = AuditLog.objects.filter(
        user=user
    ).order_by("-created_at")[:50]

    documents_to_sign = Document.objects.filter(
        signatures__user=user
    ).distinct()

    return render(
        request,
        "lawyer/dashboard.html",
        {
            "logs": logs,
            "documents": documents_to_sign
        }
    )
