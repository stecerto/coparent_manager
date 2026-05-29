import logging

from crispy_forms.layout import HTML
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.template.loader import render_to_string

from accounts.forms import UserForm, UserProfileForm
from accounts.models import UserProfile
from calendar_app.services.calendar_service import get_family_events
from core.choices import RoleChoices
from families.decorators import role_required
from documents.models import AuditLog, Document
from expenses.models import Expense
from expenses.services.expences_service import create_expense
from families.forms import InvitationForm, ChildSupportAgreementForm
from families.models import FamilyMember, Invitation, ChildSupportAgreement, Family
from families.services.balance_service import calculate_family_balance
from families.services.invitation_service import accept_invitation, \
    build_whatsapp_link
from families.utils import calculate_setup_progress, get_user_role_in_family
from families.utils import get_family_of_user, is_lawyer
from families.utils import is_parent
from accounts.models import User

# families/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Count, Q, F
from django.http import HttpResponse
from django.utils import timezone
import csv
from datetime import datetime, timedelta

from families.models import FamilyMember, Family
from core.choices import RoleChoices
from expenses.models import Expense, ExpenseCategory


@login_required
@role_required(RoleChoices.LAWYER_A, RoleChoices.LAWYER_B)
def lawyer_expenses_dashboard_view(request, family_id=None):
    """
    Dashboard expenses per avvocati:
    - /families/lawyer/expenses/ → lista famiglie (se ne ha più di una)
    - /families/lawyer/expenses/<family_id>/ → dashboard expenses della famiglia
    """
    user = request.user

    # 🔍 Trova tutte le famiglie dove l'utente è avvocato
    lawyer_memberships = FamilyMember.objects.filter(
        user=user,
        role__in=[RoleChoices.LAWYER_A, RoleChoices.LAWYER_B]
    ).select_related('family')

    # Se non ha famiglie, mostra messaggio
    if not lawyer_memberships.exists():
        return render(request, 'families/lawyer/no_families.html', {
            'message': 'Non hai famiglie assegnate per gestire le expenses.'
        })

    # Se non è specificata family_id e l'avvocato ha una sola famiglia, redirect automatico
    if not family_id and lawyer_memberships.count() == 1:
        return redirect('families:lawyer_expenses', family_id=lawyer_memberships.first().family.id)

    # Se non è specificata family_id e ha più famiglie, mostra selector
    if not family_id:
        return render(request, 'families/lawyer/expenses_family_selector.html', {
            'assigned_families': lawyer_memberships,
        })

    # 🔐 Verifica che l'avvocato abbia accesso a questa famiglia
    membership = get_object_or_404(
        FamilyMember,
        user=user,
        family_id=family_id,
        role__in=[RoleChoices.LAWYER_A, RoleChoices.LAWYER_B]
    )
    family = membership.family

    # 🎯 FILTRI (da querystring)
    status_filter = request.GET.get('status', 'all')  # all, pending, approved, rejected, paid
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    category_filter = request.GET.get('category', 'all')
    created_by_filter = request.GET.get('created_by', 'all')  # parent_a, parent_b, all

    # 🎯 QUERY BASE
    expenses_qs = Expense.objects.filter(family=family, is_active=True).select_related(
        'created_by__profile', 'category', 'approved_by', 'rejected_by'
    ).prefetch_related('payments', 'attachments')

    # Applica filtri
    if status_filter != 'all':
        expenses_qs = expenses_qs.filter(status=status_filter)
    if date_from:
        expenses_qs = expenses_qs.filter(expense_date__gte=date_from)
    if date_to:
        expenses_qs = expenses_qs.filter(expense_date__lte=date_to)
    if category_filter != 'all':
        expenses_qs = expenses_qs.filter(category_id=category_filter)
    if created_by_filter == 'parent_a':
        expenses_qs = expenses_qs.filter(created_by__family_memberships__family=family,
                                         created_by__family_memberships__role=RoleChoices.PARENT_A)
    elif created_by_filter == 'parent_b':
        expenses_qs = expenses_qs.filter(created_by__family_memberships__family=family,
                                         created_by__family_memberships__role=RoleChoices.PARENT_B)

    expenses = expenses_qs.order_by('-expense_date')

    # 📊 STATISTICHE AGGREGATE
    stats = {
        'total': expenses_qs.aggregate(total=Sum('amount'))['total'] or 0,
        'pending': expenses_qs.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0,
        'approved': expenses_qs.filter(status='approved').aggregate(total=Sum('amount'))['total'] or 0,
        'rejected': expenses_qs.filter(status='rejected').aggregate(total=Sum('amount'))['total'] or 0,
        'paid': expenses_qs.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0,
        'count': expenses_qs.count(),
        'pending_count': expenses_qs.filter(status='pending').count(),
    }

    # 📈 DATI PER GRAFICI
    # Expenses per categoria
    category_data = expenses_qs.values('category__name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

    # Expenses per mese (ultimi 6 mesi)
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_data = expenses_qs.filter(
        expense_date__gte=six_months_ago
    ).extra(select={'month': "DATE_FORMAT(expense_date, '%%Y-%%m')"}).values('month').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('month')

    # 👶 INFO MANTENIMENTO FIGLI (se il tuo modello lo supporta)
    maintenance_info = {}
    for child in family.children.filter(is_active=True):
        # Esempio: calcola spese condivise per questo figlio
        shared = expenses_qs.filter(
            shared_with_children=True,
            # Aggiungi filtro per figlio specifico se hai il campo
        ).aggregate(total=Sum('amount'))['total'] or 0

        maintenance_info[child.name] = {
            'age': child.age if hasattr(child, 'age') else 'N/D',
            'shared_expenses': shared,
            # Aggiungi altri campi se necessario
        }

    # 📋 CATEGORIE E UTENTI PER FILTRI
    categories = ExpenseCategory.objects.filter(family=family).order_by('name')
    parents = FamilyMember.objects.filter(
        family=family,
        role__in=[RoleChoices.PARENT_A, RoleChoices.PARENT_B]
    ).select_related('user').order_by('role')

    # 🎯 CONTESTO
    context = {
        'family': family,
        'membership': membership,
        'expenses': expenses,
        'stats': stats,
        'category_data': list(category_data),
        'monthly_data': list(monthly_data),
        'maintenance_info': maintenance_info,
        'categories': categories,
        'parents': parents,
        # Filtri attuali (per mantenerli nel form)
        'filters': {
            'status': status_filter,
            'date_from': date_from,
            'date_to': date_to,
            'category': category_filter,
            'created_by': created_by_filter,
        },
        # URL per export
        'export_csv_url': f"{request.path}?export=csv&{request.GET.urlencode()}",
        'export_pdf_url': f"{request.path}?export=pdf&{request.GET.urlencode()}",
    }

    # 📥 EXPORT CSV (se richiesto)
    if request.GET.get('export') == 'csv':
        return export_expenses_csv(expenses, family)

    if request.GET.get('export') == 'pdf':
        return export_expenses_pdf(expenses, family, stats)

    if request.GET.get('export') == 'pdf':
        html_string = render_to_string('families/lawyer/expenses_pdf.html', {
            'family': family,
            'expenses': expenses,
            'stats': stats,
            'generated_at': timezone.now(),
            'lawyer_name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
        })

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="spese_{family.slug}_{timezone.now().date()}.pdf"'

        HTML(string=html_string).write_pdf(response)
        return response
    return render(request, 'families/lawyer/expenses_dashboard.html', context)


def export_expenses_pdf(expenses_qs, family, stats):
    from django.template.loader import render_to_string
    from weasyprint import HTML

    html = render_to_string('families/lawyer/expenses_pdf.html', {
        'expenses': expenses_qs,
        'family': family,
        'stats': stats,
        'generated_at': timezone.now()
    })

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="expenses_{family.slug}.pdf"'

    HTML(string=html).write_pdf(response)
    return response

def export_expenses_csv(expenses_qs, family):
    """Genera CSV per download expenses"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="expenses_{family.slug}_{timezone.now().date()}.csv"'
    response.write('\ufeff'.encode('utf8'))  # BOM per Excel

    writer = csv.writer(response)
    writer.writerow([
        'Data', 'Categoria', 'Descrizione', 'Importo (€)', 'Stato',
        'Creato da', 'Approvato da', 'Rifiutato da', 'Note'
    ])

    for exp in expenses_qs:
        writer.writerow([
            exp.expense_date.strftime('%d/%m/%Y') if exp.expense_date else '',
            exp.category.name if exp.category else '',
            exp.description or '',
            f"{exp.amount:.2f}",
            exp.get_status_display(),
            exp.created_by.display_name if hasattr(exp.created_by, 'display_name') else exp.created_by.username,
            exp.approved_by.display_name if exp.approved_by and hasattr(exp.approved_by, 'display_name') else '',
            exp.rejected_by.display_name if exp.rejected_by and hasattr(exp.rejected_by, 'display_name') else '',
            exp.notes or ''
        ])

    return response


@user_passes_test(is_lawyer)
def lawyer_dashboard(request):
    pass


@user_passes_test(is_parent)
def family_dashboard(request):
    pass

@login_required
def setup_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    family = get_family_of_user(user)
    if not family:
        messages.warning(request, "Nessuna famiglia associata.")
        return redirect("home")

    # 📝 Form Utente & Profilo
    form_user = UserForm(request.POST or None, instance=user)
    form_profile = UserProfileForm(request.POST or None, instance=profile, role=user.profile.role if hasattr(user, 'userprofile') else None)

    # 👶 Formset Figli (modelformset_factory è più sicuro di formset_factory)
    # ✅ PRE-CALCOLA I FIGLI ATTIVI (così il template è semplice)
    #active_children = family.children.filter(is_active=True).order_by("birth_date", "name")

    if request.method == "POST":
        if form_user.is_valid() and form_profile.is_valid():
            form_user.save()
            profile = form_profile.save(commit=False)
            profile.setup_complete = True
            profile.save()
            messages.success(request, "✅ Dati personali salvati!")
            return redirect("families:summary")
        else:
            messages.error(request, "⚠️ Correggi gli errori evidenziati")

    # ✅ Calcola progresso setup
    progress_pct, completed, missing,important_fields, labels = calculate_setup_progress(user)
    total_fields = len([f for f in ['address', 'phone', 'birth_place'] if True])  # Base
    if getattr(profile, 'role', None) == 'lawyer':
        total_fields += 1  # + firm_name

    progress_message = {
        100: "🎉 Profilo completo! Pronto per usare CoParentManager.",
        75: "✅ Quasi fatto! Completa gli ultimi dettagli.",
        50: "👍 Buon lavoro! Continua così.",
    }.get(progress_pct // 25 * 25, "🚀 Inizia compilando i primi campi.")

    context = {
        "form_user": form_user,
        "form_profile": form_profile,
        "family": family,
        "active_children": family.children.filter(is_active=True).order_by("birth_date", "name"),  # ✅ PASSA QUESTO AL TEMPLATE
        "is_edit_mode": True,
        "membership": FamilyMember.objects.filter(family=family, user=request.user).first(),

        "setup_progress_pct": progress_pct,
        "setup_completed_count": completed,
        "setup_missing_count": missing,  # ✅ PASSA QUESTO
        "setup_total_fields": len(important_fields),  # o calcolalo qui
        "setup_completed_labels": labels,
        "setup_progress_message": progress_message,
    }

    return render(request, "families/setup.html", context)



@login_required
def family_summary(request):
    user = request.user
    profile = user.profile  # UserProfile collegato all'utente

    # ✅ RUOLO DELL'UTENTE: viene da UserProfile.role
    user_role = profile.role  # 'parent_a', 'parent_b', 'lawyer_a', 'lawyer_b'

    # 🎯 1. prendi membership corretta (UNICA VERITÀ)
    membership = (
        FamilyMember.objects
        .select_related("family", "user")
        .filter(user=user)
        .order_by("-is_primary", "-joined_at")
        .first()
    )

    if not membership:
        return render(request, "families/summary.html", {
            "error": "Nessuna famiglia associata"
        })

    family = membership.family if membership else None


    # 🎯 2. Pre-carica tutti i dati (GENITORI, AVVOCATI, FIGLI)
    other_parent = parent_a = parent_b = lawyer_a_member = lawyer_b_member = None
    if family:
        other_parent = FamilyMember.objects.filter(
            family=family,
            role__in=['parent_a', 'parent_b']
        ).exclude(user=user).select_related('user__profile').first()
        parent_a = FamilyMember.objects.filter(family=family, role=RoleChoices.PARENT_A).select_related(
            'user__profile').first()
        parent_b = FamilyMember.objects.filter(family=family, role=RoleChoices.PARENT_B).select_related(
            'user__profile').first()
        lawyer_a_member = FamilyMember.objects.filter(family=family, role=RoleChoices.LAWYER_A).select_related(
            'user__profile').first()
        lawyer_b_member = FamilyMember.objects.filter(family=family, role=RoleChoices.LAWYER_B).select_related(
            'user__profile').first()

        # ✅ FIX ERRORE TEMPLATE: calcoliamo count nella view
    children_qs = family.children.filter(is_active=True) if family else []
    children_count = children_qs.count()

    # 🎯 3. GESTIONE POST (Salva e Continua)
    if request.method == "POST":
        messages.success(request, "✅ Dati confermati!")

        # 🔀 SMISTAMENTO IN BASE AL RUOLO
        if user_role in ['parent_a', 'parent_b']:
            return redirect("families:family_dashboard")
        elif user_role in ['lawyer_a', 'lawyer_b']:
            return redirect("families:lawyer_dashboard")
        else:
            return redirect("families:summary")  # Fallback




    # ✅ CONTESTO PULITO PER IL TEMPLATE
    context = {
        'profile': profile,
        'user_role': user_role,
        'user_role_label': RoleChoices(user_role).label if user_role in RoleChoices.values else 'Utente',
        'family_name': family.name if family else '',

        # Dati già pronti - il template fa solo display
        'other_parent': other_parent,
        'parent_a': parent_a,
        'parent_b': parent_b,
        'lawyer_a_member': lawyer_a_member,
        'lawyer_b_member': lawyer_b_member,

        # RoleChoices per i label
        'RoleChoices': RoleChoices,
        "children": children_qs,
        'children_count': children_count,  # ✅ Usa questo nel template
        'membership': membership,
    }
    return render(request, 'families/summary.html', context)






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

    #profile = request.user.userprofile

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
        user_role=user_role,
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
            target = invitation.email or invitation.phone
            invitation.display_name = display_name
            invitation.save()

        # 🔥 OUTSIDE TRANSACTION
        if invitation.channel == "email":
            email_context = build_invitation_context(invitation, request.user, request.user.profile)
            send_invitation_email(request, invitation, context_extra=email_context)

            role_label = dict(RoleChoices.choices).get(invitation.role, invitation.role)
            messages.success(request, f"✅ Invito inviato a {target} come {role_label}")
            return redirect("families:family_dashboard")

        if invitation.channel == "whatsapp":
            wa_link = build_whatsapp_link(request, invitation)
            messages.success(request, f"✅ Invito inviato a {target}!")
            return redirect(wa_link)

    return render(request, "families/invite_member.html", {"form": form})


# =========================
# ACCETTA INVITO
# =========================
import logging
from django.contrib import messages
from families.services.invitation_service import accept_invitation
logger = logging.getLogger(__name__)
# families/views.py - accept_invite_view
def accept_invite_view(request, token):


    invitation = Invitation.objects.filter(
        token=token,
        status="pending"
    ).select_related('family','invited_by').first()

    if not invitation:
        return render(request, "accounts/activation_invalid.html", {"reason": "invalid"})

    if invitation.is_expired:
        invitation.mark_expired()
        return render(request, "accounts/activation_invalid.html", {"reason": "expired"})

    # ✅ CONTROLLA SE L'EMAIL È GIÀ REGISTRATA
    from django.contrib.auth import get_user_model
    User = get_user_model()
    existing_user = User.objects.filter(email=invitation.email).first()

    if existing_user:
        # ✅ Email già registrata → mostra pagina intermedia
        return render(request, "families/invite_existing_account.html", {
            "invitation": invitation,
            "existing_user": existing_user
        })

    # ✅ SE L'UTENTE È GIÀ LOGGATO → ACCETTA SUBITO
    if request.user.is_authenticated:
        try:
            accept_invitation(invitation, request.user)
            messages.success(request, f"✅ Sei stato aggiunto a '{invitation.family.name}'")
            # Redirect in base al ruolo
            if request.user.profile.role in RoleChoices.lawyer_roles():
                return redirect('families:lawyer_dashboard')
            return redirect('families:family_dashboard')
        except Exception as e:
            messages.error(request, f"⚠️ Errore nell'accettazione: {e}")
            return redirect('home')

    # ✅ SE NON È LOGGATO → SALVA TOKEN E REDIRIGI AL LOGIN
    request.session["pending_invite_token"] = str(token)
    return redirect('accounts:login')

def register_member_after_signup(request, user):
    invitation_id = request.session.get("invitation_id")

    if not invitation_id:
        return

    invitation = Invitation.objects.filter(
        id=invitation_id,
        status="pending"
    ).first()

    if invitation:
        accept_invitation(invitation, user)

    request.session.pop("invitation_id", None)
    #request.session.pop("invited_role", None)


@login_required
def resend_invitation_view(request, invitation_id):
    invitation = Invitation.objects.filter(
        id=invitation_id,
        family=get_family_of_user(request.user)
    ).first()

    if not invitation or invitation.status != "pending":
        messages.error(request, "⚠️ Invito non trovato o non più pendente")
        return redirect("families:family_dashboard")

    email_context = build_invitation_context(invitation, request.user, request.user.userprofile)

    send_invitation_email(
        request,
        invitation,
        template="emails/invitation_email.html",
        context_extra=email_context
    )

    invitation.increment_resend()
    messages.success(request, "✅ Invito reinviato!")
    return redirect("families:family_dashboard")


@login_required
def cancel_invitation_view(request, invitation_id):
    invitation = Invitation.objects.filter(id=invitation_id).first()

    if invitation and invitation.status == "pending":
        invitation.status = "cancelled"
        invitation.save()
        messages.success(request, "✅ Invito annullato")
    else:
        messages.error(request, "⚠️ Impossibile annullare l'invito")

    return redirect("families:family_dashboard")


@login_required
def dashboard_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
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
        "show_setup_banner": profile and not profile.setup_complete,
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
'''
# =========================
# SUMMARY VIEW
# =========================
@login_required
def summary_view(request):

    user = request.user

    profile = UserProfile.objects.get(user=user)

    # 1. prendo membership reale (fonte unica verità)
    membership = (
        FamilyMember.objects
        .select_related("family")
        .filter(user=user)
        .order_by("-is_primary", "-joined_at")
        .first()
    )

    if not membership:
        return render(request, "families/summary.html", {
            "profile": profile,
            "family": None,
            "children": [],
            "error": "Nessuna famiglia associata"
        })

    family = membership.family

    # 2. figli coerenti con family reale
    children = family.children.filter(is_active=True)

    context = {
        "profile": profile,
        "family": family,
        "children": children,

        # DEBUG utile
        "membership": membership,
        "user_role": membership.role,
        "debug_family_id": family.id,
    }

    return render(request, "families/summary.html", context)
'''
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
@role_required(RoleChoices.LAWYER_A, RoleChoices.LAWYER_B)
def lawyer_dashboard_view(request):
    user = request.user
    profile = user.profile

    # Verifica che sia un avvocato (sicurezza aggiuntiva)
    if profile.role not in RoleChoices.lawyer_roles():
        return render(request, '403.html', {'message': 'Accesso riservato agli avvocati'}, status=403)

    # 🔍 Trova tutte le famiglie dove l'utente è avvocato (A o B)
    lawyer_memberships = FamilyMember.objects.filter(
        user=user,
        role__in=[RoleChoices.LAWYER_A, RoleChoices.LAWYER_B]
    ).select_related('family')

    logs = AuditLog.objects.filter(
        user=user
    ).order_by("-created_at")[:50]

    documents_to_sign = Document.objects.filter(
        signatures__user=user
    ).distinct()
    families = [m.family for m in lawyer_memberships]

    # 📊 Statistiche rapide (opzionali ma utili)
    total_cases = len(families)
    active_children = sum(family.children.filter(is_active=True).count() for family in families)

    # Pre-carica l'assistito per ogni famiglia assegnata
    families_with_clients = []
    for membership in lawyer_memberships:
        expected_parent = RoleChoices.PARENT_A if membership.role == RoleChoices.LAWYER_A else RoleChoices.PARENT_B
        client = FamilyMember.objects.filter(
            family=membership.family,
            role=expected_parent
        ).select_related('user').first()

        families_with_clients.append({
            'membership': membership,
            'family': membership.family,
            'client': client.user if client else None,
        })

    context = {
        'profile': profile,
        'user_role_label': RoleChoices(profile.role).label,  # Es: "Avvocato A"
        'assigned_families': lawyer_memberships,  # Queryset con info ruolo e famiglia
        'families_list': families,  # Lista semplice di oggetti Family
        "logs": logs,
        "documents": documents_to_sign,
        'families_with_clients': families_with_clients,
        'selected_family_data': families_with_clients[0] if families_with_clients else None, # ✅ Per barra contesto (se una sola famiglia)
        'stats': {
            'total_families': total_cases,
            'total_children': active_children,
        }
    }
    return render(request, "families/lawyer/lawyer_dashboard.html", context) # 'families/lawyer/lawyer_dashboard.html', context)