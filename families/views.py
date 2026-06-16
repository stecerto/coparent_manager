# families/views.py
import csv
import logging
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import date

from children.forms import ChildSupportForm
from children.models import ChildSupport
from families.forms import SpouseSupportForm  # Assicurati che questo form esista
from .utils import get_family_of_user  # o il tuo metodo per ottenere la famiglia

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

# App locali
from accounts.forms import UserForm, UserProfileForm
from accounts.models import User, UserProfile
from calendar_app.services.calendar_service import get_family_events
from chat.models import FamilyMessage
from core.choices import RoleChoices
from documents.models import AuditLog, Document
from expenses.models import Expense, ExpenseCategory
from families.decorators import role_required
from families.forms import InvitationForm, ChildSupportAgreementForm
from families.models import Family, Invitation, ChildSupportAgreement, FamilyMember
from families.services.balance_service import calculate_family_balance
from families.services.email_service import send_invitation_email, build_invitation_context
from families.services.invitation_service import (
    build_whatsapp_link,
    accept_invitation
)
from families.utils import (
    calculate_setup_progress,
    generate_family_name,
    get_target_role,
    get_lawyer_limits,
    get_family_of_user
)




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



logger = logging.getLogger(__name__)
@login_required
def family_dashboard(request):  # ← Assicurati che prenda 'request'
    logger.info(
        f"🔍 family_dashboard: GET={request.GET.get('family_id')}, SESSION={request.session.get('active_family_id')}")
    user = request.user
    # ✅ PASSA request a get_family_of_user
    family = get_family_of_user(user, request=request)  # ← AGGIUNGI request=request

    if not family:
        return redirect("families:setup")

    active_membership = FamilyMember.objects.filter(
        family=family, user=user
    ).select_related('user').first()

    if active_membership:
        role_raw = getattr(active_membership.role, 'value', active_membership.role)
        role_label = str(role_raw).replace('_', ' ').title()
    else:
        role_label = ""

    from core.services.dashboard_service import get_upcoming_events, get_pending_documents
    upcoming_events = get_upcoming_events(family, limit=5)
    pending_documents = get_pending_documents(family, limit=5)

    context = {
        "family": family,
        # ✅ BADGE DINAMICO
        "active_family": family,
        "active_family_membership": active_membership,
        # ✅ variabili semplificate per il template
        "active_family_name": family.name,
        "active_role_label": role_label,
        "active_is_parent_a": active_membership.role == "parent_a" if active_membership else False,
        "active_is_lawyer_a": active_membership.role == "lawyer_a" if active_membership else False,
        # ✅ Dati per i widget
        "upcoming_events": upcoming_events,
        "pending_documents": pending_documents,
    }
    return render(request, "families/family_dashboard.html", context)


@login_required
def setup_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # ✅ CORRETTO: usa is_professional (True per lawyer, mediator, consultant)
    is_professional = profile.role in [RoleChoices.LAWYER, RoleChoices.MEDIATOR, RoleChoices.CONSULTANT]

    # ✅ AVVOCATI: non richiedono famiglia
    family = None if is_professional else get_family_of_user(user, request=request)



    # 📝 Form Utente & Profilo
    form_user = UserForm(request.POST or None, instance=user)

    # ✅ CORRETTO: passa profile.role (non user.profile.role)
    form_profile = UserProfileForm(
        request.POST or None,
        instance=profile,
        role=profile.role  # ← CORRETTO: passa 'lawyer', 'mediator', ecc.
    )

    if request.method == "POST":
        if form_user.is_valid() and form_profile.is_valid():
            form_user.save()
            profile = form_profile.save(commit=False)


            # ✅ CREA FAMIGLIA PER GENITORI (se non esiste)
            if not is_professional and not family:
                family_name = generate_family_name(user)
                family = Family.objects.create(
                    name=family_name,
                    created_by=user,
                    creator_role="parent_a"
                )
                FamilyMember.objects.create(
                    family=family,
                    user=user,
                    role="parent_a",
                    is_primary=True
                )
                messages.success(request, f"✅ Famiglia '{family_name}' creata!")
            else:
                messages.success(request, "✅ Dati personali salvati!")
            #salvo il profilo
            profile.setup_complete = True
            profile.save()
            messages.success(request, "✅ Dati personali salvati!")


            # ✅ Redirect in base al ruolo
            if is_professional:
                return redirect("families:professional_dashboard")
            else:
                return redirect("families:summary")
        else:
            messages.error(request, "⚠️ Correggi gli errori evidenziati")

    # ✅ Calcola progresso setup
    progress_pct, completed, missing, important_fields, labels = calculate_setup_progress(user)

    progress_message = {
        100: "🎉 Profilo completo! Pronto per usare CoParentManager.",
        75: "✅ Quasi fatto! Completa gli ultimi dettagli.",
        50: "👍 Buon lavoro! Continua così.",
    }.get(progress_pct // 25 * 25, "🚀 Inizia compilando i primi campi.")

    # ✅ active_children solo se family esiste
    active_children = family.children.filter(is_active=True).order_by("birth_date", "name") if family else []
    for child in active_children:
        # 1. Ottieni il valore, gestendo il caso in cui sia None o una stringa
        pct_a_raw = getattr(child, 'contribution_pct_parent_a', None)

        try:
            pct_a = float(pct_a_raw) if pct_a_raw is not None else 50.0
        except (ValueError, TypeError):
            pct_a = 50.0  # Fallback di sicurezza

        # 2. Calcola la percentuale B e arrotonda a 1 decimale per estetica (evita 49.9999%)
        child.pct_a_display = round(pct_a, 1)
        child.pct_b_display = round(100.0 - pct_a, 1)

    # ✅ Recupera l'accordo di mantenimento attivo (per mostrare il feedback nel setup)
    current_support = None
    if family:
        from children.models import ChildSupport
        current_support = ChildSupport.objects.filter(
            family=family,
            support_type='child',
            is_active=True
        ).order_by('-start_date').first()

    context = {
        "form_user": form_user,
        "form_profile": form_profile,
        "family": family,
        "is_lawyer": is_professional,  # ✅ CORRETTO: usa is_professional
        "is_professional": is_professional,  # ✅ Aggiungiamo anche questa per chiarezza
        "active_children": active_children,
        "is_edit_mode": True,
        "membership": FamilyMember.objects.filter(family=family, user=request.user).first() if family else None,

        "setup_progress_pct": progress_pct,
        "setup_completed_count": completed,
        "setup_missing_count": missing,
        "setup_total_fields": len(important_fields),
        "setup_completed_labels": labels,
        "setup_progress_message": progress_message,
        "current_support": current_support,
    }

    # ✅ CORRETTO: usa is_professional per decidere il template
    template = "families/lawyer_setup.html" if is_professional else "families/setup.html"
    return render(request, template, context)


@login_required
def family_settings_view(request):
    """
    Vista in sola lettura delle impostazioni della famiglia.
    Accessibile solo a professionisti (avvocati, mediatori, consulenti).
    """
    family_id = request.GET.get('family_id')
    if not family_id:
        messages.error(request, "⚠️ Famiglia non specificata")
        return redirect('families:professional_dashboard')

    family = get_object_or_404(Family, id=family_id)

    # Verifica che l'utente sia un professionista assegnato a questa famiglia
    membership = FamilyMember.objects.filter(
        family=family,
        user=request.user,
        role__in=['lawyer_a', 'lawyer_b', 'mediator', 'consultant']
    ).first()

    if not membership:
        messages.error(request, "⚠️ Non hai i permessi per accedere a questa famiglia")
        return redirect('families:professional_dashboard')

    # Recupera i dati della famiglia
    children = family.children.filter(is_active=True).order_by('birth_date', 'name')
    parents = family.members.filter(role__in=['parent_a', 'parent_b']).select_related('user')

    # Recupera l'accordo di mantenimento attivo
    from children.models import ChildSupport
    current_support = ChildSupport.objects.filter(
        family=family,
        support_type='child',
        is_active=True
    ).order_by('-start_date').first()

    context = {
        'family': family,
        'membership': membership,
        'children': children,
        'parents': parents,
        'current_support': current_support,
        'is_professional': True,  # Flag per il template
        'read_only': True,  # Modalità sola lettura
    }

    return render(request, 'families/lawyer/family_settings.html', context)

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
            return redirect("families:professional_dashboard")
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


@login_required
def spousal_support_view(request):
    """Gestione del mantenimento al coniuge (livello Famiglia)"""
    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect("families:setup")

    if request.method == "POST":
        form = SpouseSupportForm(request.POST)
        if form.is_valid():
            # 1. Disattiva eventuali mantenimenti coniuge precedenti
            ChildSupport.objects.filter(
                family=family,
                support_type='spouse',
                is_active=True
            ).update(is_active=False)

            # 2. Crea il nuovo record
            ChildSupport.objects.create(
                family=family,
                child=None,  # ✅ Nessuno figlio
                support_type='spouse',  # ✅ Tipologia corretta
                amount=form.cleaned_data['amount'],
                start_date=form.cleaned_data['start_date'],
                is_active=True,
                version=1
            )
            messages.success(request, "✅ Mantenimento al coniuge aggiornato con successo.")
            return redirect('families:family_dashboard')  # O il nome della tua url della dashboard
    else:
        # Pre-compila con l'ultimo importo attivo
        current = ChildSupport.objects.filter(
            family=family,
            support_type='spouse',
            is_active=True
        ).order_by('-start_date').first()

        initial_data = {'amount': current.amount, 'start_date': current.start_date} if current else {}
        form = SpouseSupportForm(initial=initial_data)

        # ✅ QUI DEVE ESSERE SCRITTO ESATTAMENTE COSÌ:
    return render(request, "families/spousal_support.html", {
        "form": form,
        "family": family,
        "current_support": current
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




# _______________________________________________________________________________________



@login_required
@transaction.atomic
def invite_member_view(request):
    # ✅ Recupera famiglia attiva (per genitori) o None (per professionisti)
    family = get_family_of_user(request.user, request=request)

    membership = FamilyMember.objects.filter(family=family, user=request.user).first() if family else None
    inviter_role = membership.role if membership else request.user.profile.role

    # ✅ FIX CRITICO: Se l'invitante è un professionista, IGNORA completamente la famiglia dalla sessione
    # I professionisti devono selezionare la famiglia dal dropdown (per mediator/consultant)
    # o non selezionarla affatto (per parent - creerà nuova famiglia)
    if request.user.profile.role in ['lawyer', 'mediator', 'consultant']:
        form_family = None  # ✅ Nessuna famiglia dalla sessione per i professionisti
        logger.info(f"👔 Professionista {request.user.email} - famiglia dalla sessione IGNORATA")
    else:
        form_family = family  # ✅ Per i genitori, usa la famiglia dalla sessione
        logger.info(
            f"👨‍👩‍👧 Genitore {request.user.email} - famiglia dalla sessione: {family.name if family else 'None'}")

    # ✅ 1. CONTROLLO LIMITI DELL'INVITANTE (se è un professionista)
    if request.method == "POST":
        invited_role_base = request.POST.get("role")  # 'parent', 'mediator', 'consultant'

        # Controlla i limiti SOLO se chi invita è un professionista
        if request.user.profile.role in ['lawyer', 'mediator', 'consultant']:
            limits = get_lawyer_limits(request.user)

            if limits:
                # Se sta invitando un genitore, consuma uno slot "famiglie"
                if invited_role_base == 'parent' and limits['families']['current'] >= limits['families']['limit']:
                    messages.error(request,
                                   f"⚠️ Hai raggiunto il limite di {limits['families']['limit']} famiglie per il tuo piano.")
                    return redirect("families:professional_dashboard")

                # Se sta invitando un mediatore, consuma uno slot "mediatori"
                elif invited_role_base == 'mediator' and limits['mediators']['current'] >= limits['mediators']['limit']:
                    messages.error(request,
                                   f"⚠️ Hai raggiunto il limite di {limits['mediators']['limit']} mediatori per il tuo piano.")
                    return redirect("families:professional_dashboard")

                # Se sta invitando un consulente, consuma uno slot "consulenti"
                elif invited_role_base == 'consultant' and limits['consultants']['current'] >= limits['consultants'][
                    'limit']:
                    messages.error(request,
                                   f"⚠️ Hai raggiunto il limite di {limits['consultants']['limit']} consulenti per il tuo piano.")
                    return redirect("families:professional_dashboard")

    # ✅ 2. Istanza il form con inviter
    form = InvitationForm(
        request.POST or None,
        user_role=inviter_role,
        family=form_family,  # ✅ Usa form_family (None per professionisti)
        inviter=request.user
    )

    # ✅ 3. PROCESSA IL FORM VALIDO
    if request.method == "POST" and form.is_valid():
        display_name = form.cleaned_data.get("display_name")
        invited_role_base = form.cleaned_data.get("role")  # Es: 'parent', 'mediator', 'consultant'

        # ✅ Il form ha già gestito target_family:
        # - None se role == 'parent'
        # - Famiglia valida se role == 'mediator' o 'consultant'
        target_family = form.cleaned_data.get("target_family")

        # 🧠 LOGICA RUOLO
        if request.user.profile.role in ['parent', 'parent_a', 'parent_b']:
            # ✅ L'invitante è un genitore: usa la funzione get_target_role
            target_role = get_target_role(invited_role_base, inviter_role)
        else:
            # ✅ L'invitante è un professionista: usa la logica nuova
            if invited_role_base == 'parent':
                target_role = 'parent_a'  # Sempre parent_a per nuovi genitori
            else:
                # Per mediator/consultant, target_family è garantito essere valido dal form
                inviter_membership = FamilyMember.objects.filter(user=request.user, family=target_family).first()
                if inviter_membership and '_b' in inviter_membership.role:
                    target_role = f"{invited_role_base}_b"
                else:
                    target_role = f"{invited_role_base}_a"

        # 💾 SALVATAGGIO
        with transaction.atomic():
            invitation = form.save(commit=False)
            invitation.family = target_family  # ✅ Sarà None per parent, o ID valido per altri
            invitation.invited_by = request.user
            invitation.role = target_role
            invitation.display_name = display_name
            invitation.save()

        target_contact = invitation.email or invitation.phone

        # 🔥 INVIO EMAIL E REDIRECT
        if invitation.channel == "email":
            email_context = build_invitation_context(invitation, request.user, request.user.profile)
            send_invitation_email(request, invitation, context_extra=email_context)

            role_label = dict(RoleChoices.choices).get(target_role, target_role)
            messages.success(request, f"✅ Invito inviato a {target_contact} come {role_label}")
            return redirect("families:professional_dashboard")

        if invitation.channel == "whatsapp":
            wa_link = build_whatsapp_link(request, invitation)
            messages.success(request, f"✅ Link WhatsApp generato per {target_contact}!")
            return redirect(wa_link)

    # ✅ 4. RENDERIZZA IL FORM (GET o POST non valido)
    return render(request, "families/invite_member.html", {"form": form})


# =========================
# ACCETTA INVITO
# =========================


def accept_invite_view(request, token):
    # 1. Normalizza il token


    # 2. Cerca l'invito
    invitation = Invitation.objects.filter(
        token=token,
        status="pending"
    ).select_related('family', 'invited_by').first()

    context = {"invitation": invitation}

    # 3. Se non esiste
    if not invitation:
        context["reason"] = "invalid"
        return render(request, "accounts/activation_invalid.html", context)

    # 4. Se è scaduto
    if invitation.is_expired:
        invitation.mark_expired()
        context["reason"] = "expired"
        return render(request, "accounts/activation_invalid.html", context)

    # ✅ 5. SE L'UTENTE È LOGGATO → ACCETTA SUBITO (priorità massima!)
    if request.user.is_authenticated:
        try:
            accept_invitation(invitation, request.user)
            messages.success(request,
                             f"✅ Sei stato aggiunto a '{invitation.family.name}' come {invitation.get_role_display()}")

            # Redirect in base al ruolo generico
            if request.user.profile.role in ['lawyer', 'mediator', 'consultant']:
                return redirect('lawyer_home')
            return redirect('home')
        except Exception as e:
            messages.error(request, f"⚠️ Errore nell'accettazione: {e}")
            return redirect('home')

    # ✅ 6. SE NON È LOGGATO → salva token e redirect al login
    request.session['pending_invite_token'] = str(invitation.token)

    # Mostra la pagina di invito con il pulsante "Registrati"
    return render(request, "families/invitation_landing.html", context)

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
        family=get_family_of_user(request.user, request=request)
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
    family = get_family_of_user(user, request=request)
    if not family:
        return redirect("families:setup")
    expenses = family.expenses.all().order_by("-expense_date")[:5]
    events = get_family_events(family)[:5]
    balance = calculate_family_balance(family)
    children = family.children.filter(is_active=True)
    total_expenses = sum(e.amount for e in expenses)
    current_spousal_support = ChildSupport.objects.filter(
        family=family, support_type='spouse', is_active=True
    ).order_by('-start_date').first()

    context = {
        "family": family,
        # ✅ Esplícito per la topbar (sovrascrive il context processor se necessario)
        "active_family": family,
        "active_family_name": family.name,
        "active_family_membership": FamilyMember.objects.filter(
            family=family, user=user
        ).select_related('user').first(),
        # ... resto del tuo context ...
        "current_spousal_support" : current_spousal_support,
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
def support_agreement_view(request):
    """Gestione dell'accordo di mantenimento (solo per genitori)"""
    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect('families:setup')

    # 🔒 Sicurezza: Solo i genitori possono modificare
    membership = FamilyMember.objects.filter(family=family, user=request.user).first()
    if membership and membership.role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']:
        messages.error(request, "⚠️ Solo i genitori possono modificare gli accordi di mantenimento.")
        return redirect('families:family_dashboard')

    # Recupera l'accordo attivo per pre-compilare il form
    current_support = ChildSupport.objects.filter(
        family=family,
        support_type='child',
        is_active=True
    ).order_by('-start_date').first()

    if request.method == "POST":
        form = ChildSupportForm(request.POST)
        if form.is_valid():
            # 1. Disattiva i precedenti accordi di mantenimento figli
            ChildSupport.objects.filter(
                family=family,
                support_type='child',
                is_active=True
            ).update(is_active=False)

            # 2. Crea il nuovo record MANUALMENTE (poiché è un forms.Form)
            ChildSupport.objects.create(
                family=family,
                support_type='child',
                amount=form.cleaned_data['amount'],
                start_date=form.cleaned_data['start_date'],
                # ✅ Aggiungi questi solo se li hai inseriti nel tuo forms.Form
                payer_role=form.cleaned_data.get('payer_role', 'parent_a'),
                split_pct_parent_a=form.cleaned_data.get('split_pct_parent_a', 50.0),
                is_active=True,
                version=1
            )

            messages.success(request, "✅ Accordo di mantenimento aggiornato con successo!")
            return redirect('families:setup')  # Torna al setup
    else:
        # Pre-compilazione del form se esiste un accordo attivo
        initial_data = {}
        if current_support:
            initial_data = {
                'amount': current_support.amount,
                'start_date': current_support.start_date,
            }
            # Aggiungi questi solo se il tuo form li include
            if hasattr(current_support, 'payer_role'):
                initial_data['payer_role'] = current_support.payer_role
            if hasattr(current_support, 'split_pct_parent_a'):
                initial_data['split_pct_parent_a'] = current_support.split_pct_parent_a

        form = ChildSupportForm(initial=initial_data)

    context = {
        'form': form,
        'family': family,
        'current_support': current_support
    }

    # ✅ Assicurati che il percorso del template sia corretto
    return render(request, 'families/support_agreement_form.html', context)

@login_required
def create_support_agreement_view(request):
    family = get_family_of_user(request.user, request=request)
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
    family = get_family_of_user(request.user, request=request)
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
    family = get_family_of_user(request.user, request=request)
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
    family = get_family_of_user(request.user, request=request)
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

@login_required
def family_timeline_view(request):
    family = get_family_of_user(request.user, request=request)

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
    profile = getattr(user, 'userprofile', None) or getattr(user, 'profile', None)

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
    return render(request, "families/professional_dashboard.html", context) # 'families/lawyer/lawyer_dashboard.html', context)

from families.services.dashboard_service import get_professional_cross_summary
@login_required
def professional_dashboard(request):
    """Dashboard per Avvocati, Mediatori e Consulenti con gestione multi-famiglia"""
    user = request.user
    # ✅ Verifica che sia un professionista
    profile = getattr(user, 'userprofile', None) or getattr(user, 'profile', None)
    if not profile:
        return redirect('families:setup')


    role_raw = profile.role
    role_str = str(role_raw).strip().lower() if role_raw else ''
    role_base = role_str.replace('_a', '').replace('_b', '')

    if role_base not in ['lawyer', 'mediator', 'consultant']:
        messages.error(request, "⚠️ Accesso riservato ai professionisti.")
        return redirect('families:family_dashboard')

    # ✅ NON usare get_family_of_user per professionisti!
    # Usa invece get_active_family che gestisce la sessione
    from families.utils import get_active_family
    active_family = get_active_family(request)

    active_membership = None
    if active_family:
        active_membership = FamilyMember.objects.filter(
            family=active_family, user=request.user
        ).select_related('user').first()

    active_family_membership = None
    if active_family:
        active_family_membership = FamilyMember.objects.filter(
            family=active_family, user=request.user
        ).select_related('user').first()

    # ✅ Ruoli professionali abilitati alla multi-gestione
    PRO_ROLES = [
        RoleChoices.LAWYER_A, RoleChoices.LAWYER_B,
        RoleChoices.MEDIATOR, RoleChoices.CONSULTANT
    ]

    memberships = FamilyMember.objects.filter(
        user=user,
        role__in=PRO_ROLES
    ).select_related('family').order_by('family__name')

    families_data = []

    for mem in memberships:
        family = mem.family

        # FamilyMessage
        # Approssimiamo i "non letti" con i messaggi privati degli ultimi 7 giorni.
        pending_exp = Expense.objects.filter(family=family, status='pending').count()

        recent_cutoff = timezone.now() - timedelta(days=7)
        unread_msg = FamilyMessage.objects.filter(
            family=family,
            recipient=user,
            created_at__gte=recent_cutoff  # ✅ Campo esistente, evita FieldError
        ).count()

        # 👶 Fetch figli (query ottimizzata)
        children_qs = family.children.filter(is_active=True).only("name", "surname")
        children_count = children_qs.count()
        children_names = ", ".join([f"{c.name} {c.surname}" for c in children_qs])

        # Etichetta ruolo (fallback sicuro)
        if hasattr(mem, 'get_role_display'):
            role_label = mem.get_role_display()
        else:
            raw_role = getattr(mem.role, 'value', mem.role)
            role_label = str(raw_role).replace('_', ' ').title()

        families_data.append({
            'family': family,
            'role_label': role_label,
            'pending_expenses': pending_exp,
            'unread_messages': unread_msg,
            'children_count': children_count,
            'children_names': children_names,
        })
    # ✅ NUOVO: Recupera riepilogo trasversale raggruppato e widget specifici
    from families.services.dashboard_service import (
        get_professional_cross_summary,
        get_mediator_active_agreements,
        get_consultant_active_assignments
    )
    cross_summary = get_professional_cross_summary(user)
    # Dati specifici per ruolo
    mediator_agreements = []
    consultant_assignments = []

    if role_base == 'mediator':
        mediator_agreements = get_mediator_active_agreements(user)
    elif role_base == 'consultant':
        consultant_assignments = get_consultant_active_assignments(user)

    context = {
        'cross_summary': cross_summary,
        'mediator_agreements': mediator_agreements,  # ✅ Solo per mediatori
        'consultant_assignments': consultant_assignments,  # ✅ Solo per consulenti
        'families_data': families_data,
        'active_family': active_family,
        'active_family_membership': active_family_membership,
        'selected_family_data': {
            'family': active_family,
            'membership': active_family_membership,
            'client': None,
        } if active_family else None,
        'stats': {
           'total_families': len(families_data),
           'total_children': sum(item['family'].children.filter(is_active=True).count() for item in families_data),
           'pending_expenses_total': sum(item['pending_expenses'] for item in families_data),
       }
    }

    return render(request, 'families/professional_dashboard.html', context)


@login_required
def professional_pending_events_view(request):
    """
    Pagina dedicata per professionisti: mostra tutti gli eventi, documenti
    e accordi in sospeso, raggruppati per famiglia.
    """
    user = request.user
    profile = getattr(user, 'profile', None)

    if not profile:
        messages.error(request, "⚠️ Accesso riservato ai professionisti.")
        return redirect('families:professional_dashboard')

    role_raw = profile.role
    role_str = str(role_raw).strip().lower() if role_raw else ''
    role_base = role_str.replace('_a', '').replace('_b', '')

    # Ora il controllo funziona per 'lawyer', 'mediator', 'consultant'
    if role_base not in ['lawyer', 'mediator', 'consultant']:
        messages.error(request, "⚠️ Accesso riservato ai professionisti.")
        return redirect('families:family_dashboard')

    from families.services.dashboard_service import get_professional_cross_summary

    # Recupera i dati raggruppati (ora include anche il family_id)
    cross_summary = get_professional_cross_summary(user, days_ahead=60)

    context = {
        'cross_summary': cross_summary,
        'total_families_with_activity': len(cross_summary),
        'total_items': sum(len(items) for items in cross_summary.values())
    }

    return render(request, 'families/professional_pending_events.html', context)


@login_required
def set_active_family(request, family_id):
    family = get_object_or_404(Family, id=family_id)

    if not FamilyMember.objects.filter(user=request.user, family=family).exists():
        return HttpResponseForbidden("Non hai accesso a questa famiglia")

    request.session['active_family_id'] = family_id
    request.session.modified = True

    if hasattr(request.session, 'save'):
        request.session.save()

    #redirect_url = f'families:family_dashboard?family_id={family_id}'
    return redirect(f'/families/dashboard/?family_id={family_id}')
    #return redirect(redirect_url)


# families/views.py


@login_required
def lawyer_exit_family_context(request):
    """Resetta il contesto famiglia per avvocati/mediatori/consulenti"""
    # Pulisci la sessione
    if 'active_family_id' in request.session:
        del request.session['active_family_id']

    # Redirect pulito alla dashboard avvocato (senza ?family_id)
    return redirect('families:professional_dashboard')

@login_required
def exit_family_context(request):
    """Pulisce il contesto famiglia e torna alla dashboard avvocato"""
    request.session.pop('active_family_id', None)
    return redirect('families:professional_dashboard')