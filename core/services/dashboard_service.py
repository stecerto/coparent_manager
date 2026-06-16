from django.utils import timezone
from datetime import timedelta

from calendar_app.models import CalendarEvent
from documents.models import Document


def get_upcoming_events(family, limit=5):
    """
    Recupera i prossimi eventi del calendario per una famiglia.
    """
    now = timezone.now()
    future_limit = now + timedelta(days=30)

    events = CalendarEvent.objects.filter(
        family=family,
        start_time__gte=now,
        start_time__lte=future_limit,
        is_active=True
    ).order_by('start_time')[:limit]

    return [
        {
            'id': event.id,
            'title': event.title,
            'date': event.start_time.strftime('%d/%m/%Y'),
            'time': event.start_time.strftime('%H:%M'),
            'type': event.get_event_type_display(),
            'icon': _get_event_icon(event.event_type),
        }
        for event in events
    ]


def get_pending_documents(family, limit=5):
    """
    Recupera i documenti in attesa di revisione o firma per una famiglia.
    """
    documents = Document.objects.filter(
        family=family,
        status__in=['review', 'approved'],
        is_active=True
    ).order_by('-updated_at')[:limit]

    return [
        {
            'id': doc.id,
            'title': doc.title,
            'status': doc.get_status_display(),
            'status_class': 'warning' if doc.status == 'review' else 'success',
            'icon': '📄',
        }
        for doc in documents
    ]


def _get_event_icon(event_type):
    """Restituisce un'icona emoji in base al tipo di evento."""
    icons = {
        'custody': '🏠',
        'support': '💶',
        'school': '🏫',
        'medical': '🏥',
        'expense': '💰',
        'legal': '⚖️',
        'holiday_a': '🏖️',
        'holiday_b': '🏖️',
        'child_event': '⚽',
        'mediation': '🤝',
        'consulting': '💼',
        'other': '📌',
    }
    return icons.get(event_type, '📅')