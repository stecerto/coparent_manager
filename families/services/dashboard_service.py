from django.utils import timezone
from datetime import timedelta
from collections import defaultdict

from calendar_app.models import CalendarEvent
from documents.models import Document, MediationAgreement
from families.models import ConsultantAssignment
from core.choices import RoleChoices


def get_professional_cross_summary(user, days_ahead=60):
    """
    Recupera eventi e documenti in attesa, RAGGRUPPATI per famiglia.
    Restituisce un dizionario: {'Nome Famiglia': {'id': 1, 'items': [...]}, ...}
    """
    from families.models import FamilyMember

    memberships = FamilyMember.objects.filter(
        user=user,
        role__in=[RoleChoices.LAWYER_A, RoleChoices.LAWYER_B, RoleChoices.MEDIATOR, RoleChoices.CONSULTANT]
    ).select_related('family')

    family_ids = [m.family_id for m in memberships]
    if not family_ids:
        return {}

    # ✅ NUOVA STRUTTURA: Tiene traccia dell'ID della famiglia
    family_data = {}
    now = timezone.now()
    future_date = now + timedelta(days=days_ahead)

    def add_to_family(family, item_dict):
        if family.name not in family_data:
            family_data[family.name] = {'id': family.id, 'items': []}
        family_data[family.name]['items'].append(item_dict)

    # 1. EVENTI FUTURI
    events = CalendarEvent.objects.filter(
        family_id__in=family_ids, start_time__gte=now, start_time__lte=future_date, is_active=True
    ).select_related('family').order_by('start_time')[:15]

    for event in events:
        add_to_family(event.family, {
            'icon': '📅', 'title': event.title,
            'date_display': event.start_time.strftime('%d/%m %H:%M'), 'color_class': 'text-info',
        })

    # 2. DOCUMENTI IN ATTESA
    documents = Document.objects.filter(
        family_id__in=family_ids, status__in=['review', 'approved'], is_active=True
    ).select_related('family').order_by('-created_at')[:15]

    for doc in documents:
        status_label = 'In Revisione' if doc.status == 'review' else 'Da Firmare'
        add_to_family(doc.family, {
            'icon': '📄', 'title': doc.title, 'date_display': status_label, 'color_class': 'text-warning',
        })

    # 3. ACCORDI DI MEDIAZIONE
    agreements = MediationAgreement.objects.filter(
        family_id__in=family_ids, status__in=['review', 'signing']
    ).select_related('family').order_by('-created_at')[:15]

    for agreement in agreements:
        status_label = 'In Revisione' if agreement.status == 'review' else 'In Firma'
        add_to_family(agreement.family, {
            'icon': '🤝', 'title': agreement.title, 'date_display': status_label, 'color_class': 'text-success',
        })

    # Ordina alfabeticamente
    return dict(sorted(family_data.items()))


def get_mediator_active_agreements(user):
    """Restituisce gli accordi di mediazione attivi gestiti dall'utente."""
    return MediationAgreement.objects.filter(
        mediator=user,
        status__in=['draft', 'review', 'signing']
    ).select_related('family').order_by('-created_at')[:5]


def get_consultant_active_assignments(user):
    """Restituisce gli incarichi di consulenza attivi dell'utente."""
    return ConsultantAssignment.objects.filter(
        consultant=user,
        is_active=True
    ).select_related('family').order_by('-start_date')[:5]