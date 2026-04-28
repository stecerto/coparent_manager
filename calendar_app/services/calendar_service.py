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
):
    event = CalendarEvent.objects.create(
        family=family,
        title=title,
        start_time=start_time,
        end_time=end_time,
        created_by=created_by,
        description=description,
        event_type=event_type,
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
        title=data.get("title"),
        description=data.get("description"),
        event_type=data.get("event_type", event.event_type),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        previous_version=event,
        version=event.version + 1,
        is_shared=event.is_shared,
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