from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.forms import modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from accounts.forms import UserForm, UserProfileForm
from accounts.models import UserProfile
from calendar_app.services.calendar_service import get_family_events
from children.forms import ChildForm
from children.models import ChildProfile
from documents.models import AuditLog, Document
from expenses.models import Expense
from families.forms import InvitationForm, ChildSupportAgreementForm
from families.models import FamilyMember, Invitation, ChildSupportAgreement, Family
from families.services.balance_service import calculate_family_balance
from expenses.services.expences_service import create_expense, update_expense
from families.services.invitation_service import create_invitation, accept_invitation, \
    build_whatsapp_link
from families.utils import get_family_of_user, is_lawyer
from families.utils import is_parent
from django.shortcuts import render, redirect
from django.contrib import messages
from django.forms import modelformset_factory
from children.models import ChildProfile
from children.forms import ChildFormSet


@user_passes_test(is_lawyer)
def lawyer_dashboard(request):
    pass


@user_passes_test(is_parent)
def family_dashboard(request):
    pass

# families/views.py - setup_view
@login_required
def setup_view(request):
    family = get_family_of_user(request.user)
    if not family:
        messages.warning(request, "Nessuna famiglia associata.")
        return redirect("families:family_dashboard")

    # ✅ PRE-CALCOLA I FIGLI ATTIVI (così il template è semplice)
    active_children = family.children.filter(is_active=True).order_by("birth_date", "name")

    form_user = UserForm(request.POST or None, instance=request.user)
    form_profile = UserProfileForm(request.POST or None, instance=request.user.userprofile)

    if request.method == "POST":
        if form_user.is_valid() and form_profile.is_valid():
            form_user.save()
            form_profile.save()
            messages.success(request, "✅ Dati personali salvati!")
            return redirect("families:family_dashboard")
        else:
            messages.error(request, "⚠️ Correggi gli errori evidenziati")

    return render(request, "families/setup.html", {
        "form_user": form_user,
        "form_profile": form_profile,
        "family": family,
        "active_children": active_children,  # ✅ PASSA QUESTO AL TEMPLATE
        "is_edit_mode": True,
        "membership": FamilyMember.objects.filter(family=family, user=request.user).first()
    })


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
        messages.error(request, "⚠️ Nessuna famiglia associata")
        return redirect("families:setup")

    profile = request.user.userprofile

    # ✅ DEBUG: Stampa cosa sta succedendo
    membership = FamilyMember.objects.filter(family=family, user=request.user).first()
    user_role = membership.role if membership else None
    #print(f"🔍 DEBUG INVITO:")
    #print(f"  - User: {request.user.email}")
    #print(f"  - Family: {family.name if family else None}")
    #print(f"  - Membership: {membership.role if membership else 'NONE'}")
    #print(f"  - Occupied roles: {set(family.members.values_list('role', flat=True)) if family else set()}")

    # ✅ Passa family e user_role al form
    form = InvitationForm(
        request.POST or None,
        user_role=profile.role,
        family=family  # 🔑 Fondamentale per filtrare i ruoli
    )

    if request.method == "POST" and form.is_valid():
        display_name = form.cleaned_data.get("display_name")

        with transaction.atomic():
            # ✅ Il form ha già calcolato il ruolo corretto → usalo direttamente
            invitation = form.save(
                commit=False,
                family=family,
                sender=request.user
            )
            invitation.display_name = display_name
            invitation.save()

        # 🔥 OUTSIDE TRANSACTION
        if invitation.channel == "email":
            email_context = build_invitation_context(request, invitation, family)
            send_invitation_email(request, invitation, context_extra=email_context)

            role_label = dict(Invitation.ROLE_CHOICES).get(invitation.role, invitation.role)
            messages.success(request, f"✅ Invito inviato a {invitation.email} come {role_label}")
            return redirect("families:family_dashboard")

        if invitation.channel == "whatsapp":
            wa_link = build_whatsapp_link(request, invitation)
            messages.success(request, "✅ Invito inviato!")
            return redirect(wa_link)

    return render(request, "families/invite_member.html", {"form": form})


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
    if not family:
        return redirect("families:setup")
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


@login_required
def create_support_agreement_view(request):
    family = get_family_of_user(request.user)
    if not family: return redirect("families:setup")

    if request.method == "POST":
        form = ChildSupportAgreementForm(request.POST, request.FILES)
        if form.is_valid():
            agreement = form.save(commit=False)
            agreement.family = family
            agreement.modified_by = request.user
            agreement.save()  # Il save() triggera la generazione eventi
            messages.success(request,
                             f"✅ Accordo salvato. Generati {agreement.calendar_events.count()} eventi nel calendario.")
            return redirect("calendar:calendar_view")
    else:
        form = ChildSupportAgreementForm()
        form.fields["children"].queryset = family.children.filter(is_active=True)

    return render(request, "families/support_agreement_form.html", {"form": form, "family": family})

@login_required
def edit_support_agreement_view(request, agreement_id):
    family = get_family_of_user(request.user)
    agreement = get_object_or_404(ChildSupportAgreement, pk=agreement_id, family=family)

    if request.method == "POST":
        form = ChildSupportAgreementForm(request.POST, request.FILES, instance=agreement)
        if form.is_valid():
            form.save()  # Il save() triggera rigenerazione eventi
            messages.success(request, "✅ Accordo aggiornato e eventi rigenerati.")
            return redirect("calendar:calendar_view")
    else:
        form = ChildSupportAgreementForm(instance=agreement)
        form.fields["children"].queryset = family.children.filter(is_active=True)

    return render(request, "families/support_agreement_form.html", {"form": form, "family": family, "is_edit": True})


@login_required
def delete_support_agreement_view(request, agreement_id):
    family = get_family_of_user(request.user)
    agreement = get_object_or_404(ChildSupportAgreement, pk=agreement_id, family=family)

    if request.method == "POST":
        agreement.is_active = False
        agreement.save()
        messages.success(request, "🗑️ Accordo archiviato.")
        return redirect("calendar:calendar_view")

    return render(request, "families/confirm_delete_agreement.html", {"agreement": agreement})
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
