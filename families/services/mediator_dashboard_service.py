from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from families.models import FamilyMember
from documents.models import MediationAgreement
from calendar_app.models import CalendarEvent


def get_mediator_dashboard_stats(user):
    """
    Statistiche specifiche per mediatori:
    - Sessioni di mediazione attive
    - Accordi in corso (draft, review, signing)
    - Verbali da approvare
    - Prossime sessioni
    """
    # Famiglie dove l'utente è mediatore
    memberships = FamilyMember.objects.filter(
        user=user,
        role='mediator'
    ).select_related('family')

    family_ids = [m.family_id for m in memberships]

    if not family_ids:
        return {
            'active_families': 0,
            'active_agreements': 0,
            'pending_verbali': 0,
            'upcoming_sessions': 0,
        }

    # Accordi di mediazione attivi
    active_agreements = MediationAgreement.objects.filter(
        family_id__in=family_ids,
        mediator=user,
        status__in=['draft', 'review', 'signing']
    ).count()

    # Verbali in attesa approvazione
    pending_verbali = MediationAgreement.objects.filter(
        family_id__in=family_ids,
        mediator=user,
        status='review'
    ).count()

    # Sessioni future (prossimi 30 giorni)
    now = timezone.now()
    upcoming_sessions = CalendarEvent.objects.filter(
        family_id__in=family_ids,
        event_type='mediation',
        start_time__gte=now,
        start_time__lte=now + timedelta(days=30),
        is_active=True
    ).count()

    return {
        'active_families': len(family_ids),
        'active_agreements': active_agreements,
        'pending_verbali': pending_verbali,
        'upcoming_sessions': upcoming_sessions,
    }


def get_mediator_active_sessions(user, limit=10):
    """Sessioni di mediazione attive"""
    memberships = FamilyMember.objects.filter(
        user=user,
        role='mediator'
    ).select_related('family')

    family_ids = [m.family_id for m in memberships]

    if not family_ids:
        return []

    now = timezone.now()
    sessions = CalendarEvent.objects.filter(
        family_id__in=family_ids,
        event_type='mediation',
        start_time__gte=now,
        is_active=True
    ).select_related('family').order_by('start_time')[:limit]

    return [
        {
            'family': s.family.name,
            'title': s.title,
            'date': s.start_time,
            'participants': s.description or 'N/D',
        }
        for s in sessions
    ]