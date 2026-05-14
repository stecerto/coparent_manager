from django.utils import timezone

from calendar_app.models import CalendarEvent


def create_event(
    family,
    title,
    start_time,
    end_time,
    created_by,
    description="",
    event_type="other",
    children=None,
    amount=None,
):
    # ✅ Assicurati che start/end siano timezone-aware
    if timezone.is_naive(start_time):
        start_time = timezone.make_aware(start_time)
    if timezone.is_naive(end_time):
        end_time = timezone.make_aware(end_time)

    event = CalendarEvent.objects.create(
        family=family,
        title=title,
        start_time=start_time,
        end_time=end_time,
        created_by=created_by,
        description=description,
        event_type=event_type,
        amount=amount,
    )

    # ✅ gestione ManyToMany CORRETTA
    if children is not None:
        event.children.set(children)

    return event


def update_event(event, user, data):
    """
    NON modifica evento originale.
    Crea nuova versione e archivia la precedente.
    """
    event.is_active = False
    event.archived_at = timezone.now()
    event.archived_by = user
    event.save()

    new_event = CalendarEvent.objects.create(
        family=event.family,
        created_by=user,
        title=data.get("title", event.title),
        description=data.get("description", event.description),
        event_type=data.get("event_type", event.event_type),
        start_time=data.get("start_time", event.start_time),
        end_time=data.get("end_time", event.end_time),
        previous_version=event,
        version=event.version + 1,
        is_shared=event.is_shared,
        amount=data.get("amount", event.amount),
    )

    children = data.get("children")

    if children is not None:
        new_event.children.set(list(children))
    else:
        new_event.children.set(event.children.all())

    return new_event

def get_family_events(family):
    return CalendarEvent.objects.filter(
        family=family,
        is_active=True
    ).order_by("start_time")