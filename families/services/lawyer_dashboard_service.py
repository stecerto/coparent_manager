from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import timedelta

from families.models import (
    FamilyMember, SpouseSupportAgreement, ChildSupportAgreement
)
from children.models import ChildSupport
from documents.models import Document
from expenses.models import Expense
from calendar_app.models import CalendarEvent


def get_lawyer_dashboard_stats(user):
    """
    Statistiche specifiche per avvocati:
    - Accordi gestiti (child + spouse)
    - Documenti da certificare
    - Spese in attesa approvazione
    - Prossime udienze/eventi
    """
    # Famiglie dove l'utente è avvocato
    memberships = FamilyMember.objects.filter(
        user=user,
        role__in=['lawyer_a', 'lawyer_b']
    ).select_related('family')

    family_ids = [m.family_id for m in memberships]

    if not family_ids:
        return {
            'total_agreements': 0,
            'certified_agreements': 0,
            'pending_documents': 0,
            'pending_expenses': 0,
            'upcoming_events': 0,
        }

    # Accordi di mantenimento figli certificati
    child_agreements = ChildSupport.objects.filter(
        family_id__in=family_ids,
        certified_by=user,
        is_active=True
    ).count()

    # Accordi mantenimento coniuge certificati
    spouse_agreements = SpouseSupportAgreement.objects.filter(
        family_id__in=family_ids,
        certified_by=user,
        is_active=True
    ).count()

    total_agreements = child_agreements + spouse_agreements

    # Documenti in attesa di firma/certificazione
    pending_docs = Document.objects.filter(
        family_id__in=family_ids,
        status__in=['review', 'pending_signature'],
        is_active=True
    ).count()

    # Spese in attesa approvazione
    pending_expenses = Expense.objects.filter(
        family_id__in=family_ids,
        status='pending',
        is_active=True
    ).count()

    # Eventi futuri (prossimi 30 giorni)
    now = timezone.now()
    upcoming = CalendarEvent.objects.filter(
        family_id__in=family_ids,
        start_time__gte=now,
        start_time__lte=now + timedelta(days=30),
        is_active=True
    ).count()

    return {
        'total_agreements': total_agreements,
        'certified_agreements': total_agreements,
        'pending_documents': pending_docs,
        'pending_expenses': pending_expenses,
        'upcoming_events': upcoming,
    }


def get_lawyer_recent_activity(user, limit=10):
    """Attività recente per l'avvocato"""
    memberships = FamilyMember.objects.filter(
        user=user,
        role__in=['lawyer_a', 'lawyer_b']
    ).select_related('family')

    family_ids = [m.family_id for m in memberships]

    if not family_ids:
        return []

    # Documenti recenti
    recent_docs = Document.objects.filter(
        family_id__in=family_ids,
        is_active=True
    ).select_related('family').order_by('-created_at')[:limit]

    activity = []
    for doc in recent_docs:
        activity.append({
            'type': 'document',
            'icon': '📄',
            'title': doc.title,
            'family': doc.family.name,
            'date': doc.created_at,
            'status': doc.get_status_display(),
        })

    return sorted(activity, key=lambda x: x['date'], reverse=True)[:limit]