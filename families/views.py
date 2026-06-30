# families/views.py
import csv
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count
from django.http import FileResponse
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from weasyprint import HTML

from accounts.forms import UserForm, UserProfileForm
from accounts.models import User, UserProfile
from calendar_app.services.calendar_service import get_family_events
from chat.models import FamilyMessage
from children.models import ChildSupport, ChildProfile
from core.choices import RoleChoices
from documents.models import AuditLog, Document
from expenses.models import Expense, ExpenseCategory
from families.decorators import role_required
from families.forms import InvitationForm
from families.forms import SpouseSupportAgreementForm
from families.forms import SpouseSupportForm  # Assicurati che questo form esista
from families.models import Family, Invitation, FamilyMember
from families.models import SpouseSupportAgreement
from families.services.balance_service import calculate_family_balance
from families.services.email_service import send_invitation_email, build_invitation_context
from families.services.export_service import export_family_data
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
def export_family_data_view(request):
    """Esporta tutti i dati della famiglia in ZIP"""
    family = get_family_of_user(request.user, request=request)

    if not family:
        messages.error(request, "Nessuna famiglia trovata")
        return redirect('home')

    try:
        zip_filename = export_family_data(family, request.user)
        zip_path = os.path.join(settings.MEDIA_ROOT, 'exports', zip_filename)

        messages.success(request, "✅ Export completato! Il download partirà a breve.")

        response = FileResponse(open(zip_path, 'rb'), as_attachment=True, filename=zip_filename)
        return response

    except Exception as e:
        messages.error(request, f"❌ Errore durante l'export: {str(e)}")
        return redirect('families:setup')


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
                return redirect('families:professional_dashboard')
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
    Vista delle impostazioni della famiglia.
    Accessibile a professionisti (avvocati, mediatori, consulenti) e genitori.
    """
    family_id = request.GET.get('family_id')
    if not family_id:
        messages.error(request, "⚠️ Famiglia non specificata")
        return redirect('families:professional_dashboard')

    family = get_object_or_404(Family, id=family_id)

    # Verifica che l'utente abbia accesso a questa famiglia
    membership = FamilyMember.objects.filter(
        family=family,
        user=request.user,
        role__in=['lawyer_a', 'lawyer_b', 'mediator', 'consultant', 'parent_a', 'parent_b']
    ).first()

    if not membership:
        messages.error(request, "⚠️ Non hai i permessi per accedere a questa famiglia")
        return redirect('families:professional_dashboard')

    # Recupera i dati della famiglia
    children = family.children.filter(is_active=True).order_by('birth_date', 'name')

    # ✅ Calcola percentuali e mantenimento per ogni figlio
    from children.models import ChildSupport
    from datetime import date
    from django.db.models import Q

    today = date.today()

    for child in children:
        # Percentuali
        pct_a = float(child.contribution_pct_parent_a or 50.0)
        if pct_a > 100:
            pct_a = 50.0
        pct_b = 100.0 - pct_a

        child.pct_a_display = round(pct_a, 1)
        child.pct_b_display = round(pct_b, 1)

        # ✅ Mantenimento specifico per questo figlio
        child.active_support = ChildSupport.objects.filter(
            child=child,
            support_type='child',
            is_active=True,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).order_by('-start_date').first()

    parents = family.members.filter(role__in=['parent_a', 'parent_b']).select_related('user')

    from families.models import SpouseSupportAgreement
    spouse_support = SpouseSupportAgreement.objects.filter(
        family=family,
        is_active=True,
        start_date__lte=today
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    ).order_by('-start_date').first()

    # ✅ DEBUG
    #if spouse_support:
        #print(f"🔍 DEBUG: spouse_support.certified_by = {spouse_support.certified_by}")

    context = {
        'family': family,
        'membership': membership,
        'children': children,
        'parents': parents,
        'spouse_support': spouse_support,  # ✅ NUOVO
        'is_professional': membership.role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant'],
    }

    return render(request, 'families/lawyer/family_settings.html', context)


@login_required
def edit_child_support_view(request, child_id):
    """Modifica mantenimento di un figlio (solo per avvocati)"""
    from django.urls import reverse
    from decimal import Decimal
    from children.models import ChildSupport

    family = get_family_of_user(request.user, request=request)
    if not family:
        messages.error(request, "⚠️ Nessuna famiglia trovata")
        return redirect('families:setup')

    child = get_object_or_404(ChildProfile, id=child_id, family=family, is_active=True)

    # ✅ Verifica permessi: solo avvocati/mediatori
    membership = FamilyMember.objects.filter(family=family, user=request.user).first()
    if not membership:
        messages.error(request, "⚠️ Non sei membro di questa famiglia")
        return redirect('families:family_dashboard')

    user_role = str(membership.role).lower()
    is_professional = user_role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']

    if not is_professional:
        messages.error(request, "⚠️ Solo gli avvocati possono modificare il mantenimento")
        return redirect('families:family_settings')

    # Recupera mantenimento attivo
    current_support = ChildSupport.objects.filter(
        child=child,
        support_type='child',
        is_active=True
    ).order_by('-start_date').first()

    if request.method == 'POST':
        amount = request.POST.get('amount')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date') or None
        payer_role = request.POST.get('payer_role', 'parent_a')
        split_pct = request.POST.get('split_pct_parent_a', 50.00)

        # ✅ CAMPI SENTENZA (obbligatori)
        decree_number = request.POST.get('decree_number', '').strip()
        decree_date = request.POST.get('decree_date')
        decree_file = request.FILES.get('decree_file')

        # ✅ Validazione campi obbligatori
        if not amount or not start_date:
            messages.error(request, "⚠️ Importo e data inizio sono obbligatori")
        elif not decree_number or not decree_date or not decree_file:
            messages.error(request, "⚠️ È obbligatorio caricare la sentenza (numero, data e file)")
        else:
            # ✅ Chiudi mantenimento precedente
            if current_support:
                current_support.is_active = False
                current_support.end_date = start_date
                current_support.save(update_fields=['is_active', 'end_date'])

            # ✅ Crea nuovo mantenimento
            new_support = ChildSupport.objects.create(
                child=child,
                family=family,
                support_type='child',
                amount=Decimal(amount),
                start_date=start_date,
                end_date=end_date,
                payer_role=payer_role,
                split_pct_parent_a=Decimal(split_pct),
                # ✅ SENTENZA
                decree_number=decree_number,
                decree_date=decree_date,
                decree_file=decree_file,
                is_active=True,
                version=(current_support.version + 1) if current_support else 1,
                previous_version=current_support,
                # ✅ CERTIFICAZIONE AUTOMATICA (perché c'è la sentenza)
                certified_by=request.user,
                certified_at=timezone.now(),
            )

            messages.success(
                request,
                f"✅ Mantenimento aggiornato e certificato per {child.name} con sentenza {decree_number}"
            )

            return redirect(f"{reverse('families:family_settings')}?family_id={family.id}")

    # ✅ ✅ ✅ FUORI dal blocco POST: gestisce sia GET che POST con errori
    context = {
        'child': child,
        'current_support': current_support,
        'family': family,
        'is_professional': is_professional,
    }

    return render(request, 'families/edit_child_support.html', context)


@login_required
def view_decree_view(request, support_id):
    """Visualizza sentenza mantenimento (accessibile a genitori e avvocati)"""
    from children.models import ChildSupport

    support = get_object_or_404(ChildSupport, id=support_id)
    family = get_family_of_user(request.user, request=request)

    # Verifica che l'utente abbia accesso alla famiglia
    if support.family != family:
        messages.error(request, "⚠️ Accesso negato")
        return redirect('families:family_dashboard')

    if not support.decree_file:
        messages.error(request, "⚠️ Nessuna sentenza caricata")
        return redirect('families:family_settings')

    # Restituisci il file
    from django.http import FileResponse
    response = FileResponse(support.decree_file.open('rb'))
    response['Content-Disposition'] = f'inline; filename="{support.decree_file.name.split("/")[-1]}"'
    return response


@login_required
def family_summary(request):
    user = request.user
    profile = user.profile

    user_role = profile.role

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

    # 🎯 2. Pre-carica tutti i dati
    other_parent = parent_a = parent_b = lawyer_a_member = lawyer_b_member = None
    mediator_member = consultant_member = None

    if family:
        other_parent = FamilyMember.objects.filter(
            family=family,
            role__in=['parent_a', 'parent_b']
        ).exclude(user=user).select_related('user__profile').first()
        parent_a = FamilyMember.objects.filter(family=family, role=RoleChoices.PARENT_A).select_related(
            'user__profile').first()
        parent_b = FamilyMember.objects.filter(family=family,
                                               role__in=['parent_b', RoleChoices.PARENT_B]).select_related(
            'user__profile').first()
        lawyer_a_member = FamilyMember.objects.filter(family=family, role=RoleChoices.LAWYER_A).select_related(
            'user__profile').first()
        lawyer_b_member = FamilyMember.objects.filter(family=family, role=RoleChoices.LAWYER_B).select_related(
            'user__profile').first()
        mediator_member = FamilyMember.objects.filter(family=family, role=RoleChoices.MEDIATOR).select_related(
            'user__profile').first()
        consultant_member = FamilyMember.objects.filter(family=family, role=RoleChoices.CONSULTANT).select_related(
            'user__profile').first()

    children_qs = family.children.filter(is_active=True) if family else []
    children_count = children_qs.count()

    # ✅ NUOVO: Calcola i conteggi nella view (non nel template)
    active_members_count = sum([
        1 if parent_a and parent_a.user else 0,
        1 if parent_b and parent_b.user else 0,
        1 if lawyer_a_member and lawyer_a_member.user else 0,
        1 if lawyer_b_member and lawyer_b_member.user else 0,
        1 if mediator_member and mediator_member.user else 0,
        1 if consultant_member and consultant_member.user else 0,
    ])

    # ✅ Calcola percentuale completamento
    completion_items = [
        1 if parent_a and parent_a.user else 0,
        1 if parent_b and parent_b.user else 0,
        1 if children_count > 0 else 0,
    ]
    completion_pct = int((sum(completion_items) / len(completion_items)) * 100)

    if request.method == "POST":
        messages.success(request, "✅ Dati confermati!")

        if user_role in ['parent_a', 'parent_b']:
            return redirect("families:family_dashboard")
        elif user_role in ['lawyer_a', 'lawyer_b']:
            return redirect('families:professional_dashboard')
        else:
            return redirect("families:summary")

    all_members = FamilyMember.objects.filter(family=family).select_related('user')

    context = {
        'profile': profile,
        'user_role': user_role,
        'user_role_label': RoleChoices(user_role).label if user_role in RoleChoices.values else 'Utente',
        'family_name': family.name if family else '',

        'other_parent': other_parent,
        'parent_a': parent_a,
        'parent_b': parent_b,
        'lawyer_a_member': lawyer_a_member,
        'lawyer_b_member': lawyer_b_member,
        'mediator_member': mediator_member,
        'consultant_member': consultant_member,

        'RoleChoices': RoleChoices,
        "children": children_qs,
        'children_count': children_count,
        'membership': membership,

        # ✅ NUOVI: Conteggi calcolati nella view
        'active_members_count': active_members_count,
        'completion_pct': completion_pct,
    }
    return render(request, 'families/summary.html', context)


@login_required
def spousal_support_view(request):
    """Gestione del mantenimento al coniuge - USA SpouseSupportAgreement"""
    from families.models import SpouseSupportAgreement
    from families.forms import SpouseSupportForm
    from decimal import Decimal

    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect("families:setup")

    # ✅ Verifica permessi: genitori O avvocati
    membership = FamilyMember.objects.filter(family=family, user=request.user).first()

    if not membership:
        messages.error(request, "⚠️ Non hai i permessi per gestire il mantenimento")
        return redirect('families:family_dashboard')

    user_role = str(membership.role).lower()
    is_professional = user_role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']
    is_parent = user_role in ['parent_a', 'parent_b']

    if not (is_parent or is_professional):
        messages.error(request, "⚠️ Non hai i permessi per gestire il mantenimento")
        return redirect('families:family_dashboard')

    # ✅ USA SpouseSupportAgreement (non ChildSupport)
    current = SpouseSupportAgreement.objects.filter(
        family=family,
        is_active=True
    ).order_by('-start_date').first()

    # ✅ BLOCCO: Se certificato E utente è genitore → REDIRECT
    if current and current.certified_by and not is_professional:
        messages.warning(
            request,
            "⚠️ Questo mantenimento è certificato. Solo un avvocato può modificarlo caricando una nuova sentenza."
        )
        return redirect('families:family_dashboard')

    if request.method == "POST":
        form = SpouseSupportForm(request.POST, request.FILES)

        if form.is_valid():
            print(f"✅ Form valido, dati: {form.cleaned_data}")

            # ✅ Verifica che ci sia il file della sentenza
            decree_file = form.cleaned_data.get('decree_file')
            print(f"📎 decree_file: {decree_file}")

            if not decree_file:
                messages.error(request, "⚠️ È obbligatorio caricare il file della sentenza")
                print("❌ Manca il file della sentenza")
            else:
                print("✅ File presente, procedo con la creazione")
                # ✅ Se esiste un accordo precedente, disattivalo
                if current:
                    current.is_active = False
                    current.save(update_fields=['is_active'])
                    new_version = current.version + 1
                else:
                    new_version = 1

                # ✅ Crea nuovo accordo con SpouseSupportAgreement
                new_agreement = SpouseSupportAgreement.objects.create(
                    family=family,
                    monthly_amount=form.cleaned_data['amount'],  # ✅ amount del form → monthly_amount del modello
                    #split_pct_parent_a=form.cleaned_data.get('split_pct_parent_a') or Decimal('50.00'),
                    payment_day=form.cleaned_data['payment_day'],
                    start_date=form.cleaned_data['start_date'],
                    end_date=form.cleaned_data.get('end_date'),
                    payer_role=form.cleaned_data['payer_role'],
                    decree_number=form.cleaned_data['decree_number'],
                    decree_date=form.cleaned_data['decree_date'],
                    decree_file=decree_file,
                    is_active=True,
                    version=new_version,
                    previous_version=current,
                    # ✅ Certificazione automatica se professionista
                    certified_by=request.user if is_professional else None,
                    certified_at=timezone.now() if is_professional else None,
                    modified_by=request.user,
                )

                if is_professional:
                    messages.success(
                        request,
                        f"✅ Sentenza registrata e certificata: €{new_agreement.monthly_amount}/mese - {form.cleaned_data['decree_number']}"
                    )
                    from django.urls import reverse
                    return redirect(f"{reverse('families:family_settings')}?family_id={family.id}")
                else:
                    messages.success(request, "✅ Mantenimento al coniuge aggiornato con successo.")
                    return redirect('families:family_dashboard')
    else:
        # ✅ Pre-compila il form con i dati dell'accordo esistente
        initial_data = {
            'amount': current.monthly_amount,  # ✅ monthly_amount del modello → amount del form
            'start_date': current.start_date,
            'end_date': current.end_date,
            'payment_day': current.payment_day,
            #'split_pct_parent_a': current.split_pct_parent_a,
            'payer_role': current.payer_role,
            'decree_number': current.decree_number,
            'decree_date': current.decree_date,
        } if current else {
            'split_pct_parent_a': 50.00,
            'payer_role': 'parent_a',
            'payment_day': 5,
        }
        form = SpouseSupportForm(initial=initial_data)

    # ✅ Prepara i nomi dei genitori per il template
    parent_a_name = "Genitore A"
    parent_b_name = "Genitore B"

    member_a = FamilyMember.objects.filter(
        family=family, role='parent_a', user__is_active=True
    ).select_related('user').first()

    member_b = FamilyMember.objects.filter(
        family=family, role='parent_b', user__is_active=True
    ).select_related('user').first()

    if member_a and member_a.user:
        parent_a_name = member_a.user.get_full_name().strip() or member_a.user.email

    if member_b and member_b.user:
        parent_b_name = member_b.user.get_full_name().strip() or member_b.user.email

    return render(request, "families/spousal_support.html", {
        "form": form,
        "family": family,
        "current_support": current,
        "is_professional": is_professional,
        "parent_a_name": parent_a_name,
        "parent_b_name": parent_b_name,
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
                    return redirect("families:lawyerl_dashboard")

                # Se sta invitando un mediatore, consuma uno slot "mediatori"
                elif invited_role_base == 'mediator' and limits['mediators']['current'] >= limits['mediators']['limit']:
                    messages.error(request,
                                   f"⚠️ Hai raggiunto il limite di {limits['mediators']['limit']} mediatori per il tuo piano.")
                    return redirect('families:professional_dashboard')

                # Se sta invitando un consulente, consuma uno slot "consulenti"
                elif invited_role_base == 'consultant' and limits['consultants']['current'] >= limits['consultants'][
                    'limit']:
                    messages.error(request,
                                   f"⚠️ Hai raggiunto il limite di {limits['consultants']['limit']} consulenti per il tuo piano.")
                    return redirect('families:professional_dashboard')

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
            return redirect('families:professional_dashboard')

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

    # ✅ NUOVO: Gestione professionisti con family_id da querystring
    family_id = request.GET.get('family_id')
    is_professional = profile.role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']

    if is_professional and family_id:
        # Imposta il contesto famiglia nella sessione
        request.session['active_family_id'] = int(family_id)
        family = get_object_or_404(Family, id=family_id)

        # Verifica che il professionista abbia accesso a questa famiglia
        membership = FamilyMember.objects.filter(
            family=family,
            user=user,
            role__in=['lawyer_a', 'lawyer_b', 'mediator', 'consultant']
        ).first()

        if not membership:
            messages.error(request, "⚠️ Non hai accesso a questa famiglia")
            return redirect('families:professional_dashboard')
    else:
        # Logica esistente per genitori
        family = get_family_of_user(user, request=request)
        if not family:
            return redirect("families:setup")
        membership = FamilyMember.objects.filter(family=family, user=user).first()

    # ✅ Calcola role_label (come in family_dashboard)
    if membership:
        role_raw = getattr(membership.role, 'value', membership.role)
        role_label = str(role_raw).replace('_', ' ').title()
    else:
        role_label = ""

    # ✅ Dati comuni
    expenses = family.expenses.all().order_by("-expense_date")[:5]
    events = get_family_events(family)[:5]
    balance = calculate_family_balance(family)
    children = family.children.filter(is_active=True)
    total_expenses = sum(e.amount for e in expenses)

    # ✅ MIGRATO A SpouseSupportAgreement
    from families.models import SpouseSupportAgreement
    current_spousal_support = SpouseSupportAgreement.objects.filter(
        family=family, is_active=True
    ).order_by('-start_date').first()

    # ✅ Widget dati (come in family_dashboard)
    from core.services.dashboard_service import get_upcoming_events, get_pending_documents
    upcoming_events = get_upcoming_events(family, limit=5)
    pending_documents = get_pending_documents(family, limit=5)

    context = {
        "family": family,
        # ✅ Esplícito per la topbar
        "active_family": family,
        "active_family_name": family.name,
        "active_family_membership": membership,
        "active_role_label": role_label,
        "active_is_parent_a": membership.role == "parent_a" if membership else False,
        "active_is_lawyer_a": membership.role == "lawyer_a" if membership else False,

        # ✅ Mantenimento coniuge
        "current_spousal_support": current_spousal_support,

        # ✅ Dati per il template
        "children": children,
        "expenses": expenses,
        "expenses_count": family.expenses.count(),
        "documents_count": family.documents.count(),
        "messages_count": family.chat.count() if hasattr(family, "chat") else 0,
        "events": events,
        "events_count": family.calendar.count() if hasattr(family, "events") else 0,
        "children_count": family.children.count(),
        "balance": balance,
        "total_expenses": total_expenses,
        "show_setup_banner": profile and not profile.setup_complete,

        # ✅ Widget dati
        "upcoming_events": upcoming_events,
        "pending_documents": pending_documents,
    }

    return render(request, "families/family_dashboard.html", context)


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
'''
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
    return render(request, 'families/lawyer/lawyer_dashboard.html', context)


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

    return render(request, 'families/lawyer_dashboard.html', context)
'''

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

    return redirect(f'/families/dashboard/?family_id={family_id}')






@login_required
def lawyer_exit_family_context(request):
    """Resetta il contesto famiglia per avvocati/mediatori/consulenti"""
    # Pulisci la sessione
    if 'active_family_id' in request.session:
        del request.session['active_family_id']

    # Redirect pulito alla dashboard avvocato (senza ?family_id)
    return redirect('families:lawyer_dashboard')


@login_required
def spouse_support_list(request):
    """Lista accordi mantenimento coniuge"""
    family = get_family_of_user(request.user, request=request)

    if not family:
        messages.error(request, "Nessuna famiglia trovata")
        return redirect('home')

    agreements = SpouseSupportAgreement.objects.filter(
        family=family,
        is_active=True
    ).select_related('beneficiary').order_by('-start_date')

    context = {
        'family': family,
        'agreements': agreements,
    }

    return render(request, 'families/spouse_support_list.html', context)


@login_required
def spouse_support_create(request):
    """Crea nuovo mantenimento coniuge - SOLO AVVOCATI con sentenza"""
    from decimal import Decimal
    from families.forms import SpouseSupportForm

    family = get_family_of_user(request.user, request=request)

    if not family:
        messages.error(request, "⚠️ Nessuna famiglia trovata")
        return redirect('families:setup')

    membership = FamilyMember.objects.filter(family=family, user=request.user).first()

    if not membership:
        messages.error(request, "⚠️ Non sei membro di questa famiglia")
        return redirect('families:family_dashboard')

    user_role = str(membership.role).lower()
    is_professional = user_role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']

    if not is_professional:
        messages.error(request, "⚠️ Solo gli avvocati possono creare il mantenimento al coniuge caricando la sentenza")
        return redirect('families:spouse_support_list')

    if request.method == 'POST':
        form = SpouseSupportForm(request.POST, request.FILES)

        if form.is_valid():
            decree_number = form.cleaned_data['decree_number']
            decree_date = form.cleaned_data['decree_date']
            decree_file = form.cleaned_data.get('decree_file')

            if not decree_file:
                messages.error(request, "⚠️ È obbligatorio caricare il file della sentenza")
            else:
                # ✅ IMPORTANTE: Disattiva TUTTI i vecchi accordi attivi PRIMA di creare il nuovo
                deactivated_count = SpouseSupportAgreement.objects.filter(
                    family=family,
                    is_active=True
                ).update(is_active=False)

                if deactivated_count > 0:
                    print(f"🔄 Disattivati {deactivated_count} accordi precedenti")

                # ✅ Crea nuova sentenza - MAPPA amount → monthly_amount
                new_agreement = SpouseSupportAgreement.objects.create(
                    family=family,
                    monthly_amount=form.cleaned_data['amount'],  # ✅ amount del form → monthly_amount del modello
                    payment_day=form.cleaned_data['payment_day'],
                    start_date=form.cleaned_data['start_date'],
                    end_date=form.cleaned_data.get('end_date'),
                    payer_role=form.cleaned_data['payer_role'],
                    decree_number=decree_number,
                    decree_date=decree_date,
                    decree_file=decree_file,
                    is_active=True,
                    version=1,
                    certified_by=request.user,
                    certified_at=timezone.now(),
                    modified_by=request.user,
                )

                # ✅ RIMOSSO: split_pct_parent_a non esiste nel modello SpouseSupportAgreement
                # Se ti serve, aggiungilo al modello o usa un campo diverso

                messages.success(
                    request,
                    f"✅ Sentenza registrata: €{new_agreement.monthly_amount}/mese - {decree_number}"
                )
                return redirect('families:spouse_support_list')
    else:
        form = SpouseSupportForm(initial={
            'payer_role': 'parent_a',
            'payment_day': 5,
        })

    context = {
        'form': form,
        'family': family,
        'title': 'Nuova Sentenza Mantenimento Coniuge',
        'is_professional': is_professional,
    }

    return render(request, 'families/spouse_support_form.html', context)


@login_required
def spouse_support_edit(request, pk):
    """Modifica mantenimento coniuge - SOLO AVVOCATI con nuova sentenza"""
    from decimal import Decimal
    from families.forms import SpouseSupportForm

    family = get_family_of_user(request.user, request=request)

    if not family:
        messages.error(request, "⚠️ Nessuna famiglia trovata")
        return redirect('families:setup')

    agreement = get_object_or_404(SpouseSupportAgreement, pk=pk, family=family)

    membership = FamilyMember.objects.filter(family=family, user=request.user).first()

    if not membership:
        messages.error(request, "⚠️ Non sei membro di questa famiglia")
        return redirect('families:family_dashboard')

    user_role = str(membership.role).lower()
    is_professional = user_role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']

    if not is_professional:
        messages.error(request, "⚠️ Solo gli avvocati possono modificare il mantenimento caricando una nuova sentenza")
        return redirect('families:spouse_support_list')

    if request.method == 'POST':
        form = SpouseSupportForm(request.POST, request.FILES)

        if form.is_valid():
            decree_number = form.cleaned_data['decree_number']
            decree_date = form.cleaned_data['decree_date']
            decree_file = form.cleaned_data.get('decree_file')

            if not decree_file:
                messages.error(request, "⚠️ Per modificare è obbligatorio caricare una nuova sentenza (file)")
            else:
                agreement.is_active = False
                agreement.save(update_fields=['is_active'])

                # ✅ Crea nuova versione - MAPPA amount → monthly_amount
                new_agreement = SpouseSupportAgreement.objects.create(
                    family=family,
                    monthly_amount=form.cleaned_data['amount'],  # ✅ amount del form → monthly_amount del modello
                    #split_pct_parent_a=form.cleaned_data['split_pct_parent_a'],
                    payment_day=form.cleaned_data['payment_day'],
                    start_date=form.cleaned_data['start_date'],
                    end_date=form.cleaned_data.get('end_date'),
                    payer_role=form.cleaned_data['payer_role'],
                    decree_number=decree_number,
                    decree_date=decree_date,
                    decree_file=decree_file,
                    version=agreement.version + 1,
                    previous_version=agreement,
                    is_active=True,
                    certified_by=request.user,
                    certified_at=timezone.now(),
                    modified_by=request.user,
                )



                messages.success(
                    request,
                    f"✅ Mantenimento aggiornato con nuova sentenza {decree_number}: €{new_agreement.monthly_amount}/mese"
                )
                return redirect('families:spouse_support_list')
    else:
        # ✅ Pre-compila con 'amount' (non 'monthly_amount')
        form = SpouseSupportForm(initial={
            'amount': agreement.monthly_amount,  # ✅ monthly_amount del modello → amount del form
            'start_date': agreement.start_date,
            'end_date': agreement.end_date,
            'payment_day': agreement.payment_day,
            #'split_pct_parent_a': agreement.split_pct_parent_a,
            'payer_role': agreement.payer_role,
            'decree_number': agreement.decree_number,
            'decree_date': agreement.decree_date,
        })

    context = {
        'form': form,
        'agreement': agreement,
        'family': family,
        'is_professional': is_professional,
        'title': 'Modifica Sentenza Mantenimento Coniuge',
    }

    return render(request, 'families/spouse_support_form.html', context)


@login_required
def view_spouse_decree_view(request, agreement_id):
    """Visualizza sentenza mantenimento coniuge (accessibile a genitori e avvocati)"""
    agreement = get_object_or_404(SpouseSupportAgreement, id=agreement_id)
    family = get_family_of_user(request.user, request=request)

    # Verifica che l'utente abbia accesso alla famiglia
    if agreement.family != family:
        messages.error(request, "⚠️ Accesso negato")
        return redirect('families:family_dashboard')

    if not agreement.decree_file:
        messages.error(request, "⚠️ Nessuna sentenza caricata")
        return redirect('families:spouse_support_list')

    # Restituisci il file
    response = FileResponse(agreement.decree_file.open('rb'))
    response['Content-Disposition'] = f'inline; filename="{agreement.decree_file.name.split("/")[-1]}"'
    return response


@login_required
def professional_dashboard(request):
    """Dashboard per Avvocati, Mediatori e Consulenti con gestione multi-famiglia"""
    user = request.user
    profile = getattr(user, 'userprofile', None) or getattr(user, 'profile', None)
    if not profile:
        return redirect('families:setup')

    role_raw = profile.role
    role_str = str(role_raw).strip().lower() if role_raw else ''
    role_base = role_str.replace('_a', '').replace('_b', '')

    if role_base not in ['lawyer', 'mediator', 'consultant']:
        messages.error(request, "⚠️ Accesso riservato ai professionisti.")
        return redirect('families:family_dashboard')

    # ✅ ROUTING INTELLIGENTE: Template specifico per ruolo
    if role_base == 'lawyer':
        return _lawyer_dashboard(request, profile, role_base)
    elif role_base == 'mediator':
        return _mediator_dashboard(request, profile, role_base)
    elif role_base == 'consultant':
        return _consultant_dashboard(request, profile, role_base)

    return render(request, 'families/lawyer_dashboard.html', {})


def _lawyer_dashboard(request, profile, role_base):
    """Dashboard specifica per avvocati"""
    from families.services.lawyer_dashboard_service import (
        get_lawyer_dashboard_stats, get_lawyer_recent_activity
    )

    user = request.user
    memberships = FamilyMember.objects.filter(
        user=user,
        role__in=['lawyer_a', 'lawyer_b']
    ).select_related('family').order_by('family__name')

    families_data = []
    for mem in memberships:
        family = mem.family
        pending_exp = Expense.objects.filter(family=family, status='pending').count()
        recent_cutoff = timezone.now() - timedelta(days=7)
        unread_msg = FamilyMessage.objects.filter(
            family=family, recipient=user, created_at__gte=recent_cutoff
        ).count()

        children_qs = family.children.filter(is_active=True).only("name", "surname")
        children_count = children_qs.count()
        children_names = ", ".join([f"{c.name} {c.surname}" for c in children_qs])

        role_label = mem.get_role_display() if hasattr(mem, 'get_role_display') else str(mem.role).replace('_',
                                                                                                           ' ').title()

        families_data.append({
            'family': family,
            'role_label': role_label,
            'pending_expenses': pending_exp,
            'unread_messages': unread_msg,
            'children_count': children_count,
            'children_names': children_names,
        })

    stats = get_lawyer_dashboard_stats(user)

    context = {
        'families_data': families_data,
        'stats': stats,
    }

    return render(request, 'families/lawyer_dashboard.html', context)


def _mediator_dashboard(request, profile, role_base):
    """Dashboard specifica per mediatori"""
    from families.services.mediator_dashboard_service import (
        get_mediator_dashboard_stats, get_mediator_active_sessions
    )

    user = request.user
    memberships = FamilyMember.objects.filter(
        user=user,
        role='mediator'
    ).select_related('family').order_by('family__name')

    families_data = []
    for mem in memberships:
        family = mem.family
        recent_cutoff = timezone.now() - timedelta(days=7)
        unread_msg = FamilyMessage.objects.filter(
            family=family, recipient=user, created_at__gte=recent_cutoff
        ).count()

        children_qs = family.children.filter(is_active=True).only("name", "surname")
        children_count = children_qs.count()
        children_names = ", ".join([f"{c.name} {c.surname}" for c in children_qs])

        role_label = mem.get_role_display() if hasattr(mem, 'get_role_display') else 'Mediatore'

        families_data.append({
            'family': family,
            'role_label': role_label,
            'unread_messages': unread_msg,
            'children_count': children_count,
            'children_names': children_names,
        })

    stats = get_mediator_dashboard_stats(user)

    context = {
        'families_data': families_data,
        'stats': stats,
    }

    return render(request, 'families/mediator_dashboard.html', context)


def _consultant_dashboard(request, profile, role_base):
    """
    Dashboard specifica per consulenti.
    Coerente con lawyer_dashboard e mediator_dashboard: usa FamilyMember.
    """
    from families.services.consultant_dashboard_service import get_consultant_dashboard_stats

    user = request.user

    # ✅ Recupera tutte le famiglie dove l'utente è consulente (via FamilyMember)
    memberships = FamilyMember.objects.filter(
        user=user,
        role='consultant'
    ).select_related('family').order_by('family__name')

    # ✅ Costruisci families_data (come per lawyer e mediator)
    families_data = []
    for mem in memberships:
        family = mem.family

        # Statistiche per questa famiglia
        children_qs = family.children.filter(is_active=True).only("name", "surname")
        children_count = children_qs.count()
        children_names = ", ".join([f"{c.name} {c.surname}" for c in children_qs])

        recent_cutoff = timezone.now() - timedelta(days=7)
        unread_msg = FamilyMessage.objects.filter(
            family=family, recipient=user, created_at__gte=recent_cutoff
        ).count()

        role_label = mem.get_role_display() if hasattr(mem, 'get_role_display') else 'Consulente'

        families_data.append({
            'family': family,
            'role_label': role_label,
            'unread_messages': unread_msg,
            'children_count': children_count,
            'children_names': children_names,
        })

    # ✅ Recupera statistiche aggregate
    stats = get_consultant_dashboard_stats(user)

    context = {
        'families_data': families_data,  # ✅ Coerente con lawyer/mediator
        'stats': stats,
    }

    return render(request, 'families/consultant_dashboard.html', context)

@login_required
def lawyer_dashboard_view(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)
    # ✅ DEBUG: Log del ruolo
    print(f"\n🔍 lawyer_dashboard_view:")
    print(f"  User: {user.email}")
    print(f"  Profile: {profile}")
    print(f"  Role: {profile.role if profile else 'None'}")
    """Wrapper: forza dashboard avvocato"""
    profile = getattr(request.user, 'profile', None)
    if not profile or str(profile.role).lower().replace('_a', '').replace('_b', '') != 'lawyer':
        messages.error(request, "⚠️ Accesso riservato agli avvocati.")
        return redirect('families:professional_dashboard')
    return _lawyer_dashboard(request, profile, 'lawyer')


@login_required
def mediator_dashboard_view(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)
    # ✅ DEBUG: Log del ruolo
    print(f"\n🔍 mediator_dashboard_view:")
    print(f"  User: {user.email}")
    print(f"  Profile: {profile}")
    print(f"  Role: {profile.role if profile else 'None'}")
    """Wrapper: forza dashboard mediatore"""
    profile = getattr(request.user, 'profile', None)
    if not profile or str(profile.role).lower().replace('_a', '').replace('_b', '') != 'mediator':
        messages.error(request, "⚠️ Accesso riservato ai mediatori.")
        return redirect('families:professional_dashboard')  # ✅ FIX: era 'families:mediator_dashboard'

    return _mediator_dashboard(request, profile, 'mediator')


@login_required
def consultant_dashboard_view(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)
    # ✅ DEBUG: Log del ruolo
    print(f"\n🔍 consultant_dashboard_view:")
    print(f"  User: {user.email}")
    print(f"  Profile: {profile}")
    print(f"  Role: {profile.role if profile else 'None'}")
    """Wrapper: forza dashboard consulente"""
    profile = getattr(request.user, 'profile', None)
    if not profile or str(profile.role).lower().replace('_a', '').replace('_b', '') != 'consultant':
        messages.error(request, "⚠️ Accesso riservato ai consulenti.")
        return redirect('families:consultant_dashboard')
    return _consultant_dashboard(request, profile, 'consultant')