from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from calendar_app.models import CalendarEvent, EventReminder
from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from calendar_app.models import CalendarEvent, EventReminder


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
        source="event",
        #linked_id=event_type.id,

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


# ✅ Usa la stringa per evitare AppRegistryNotReady
@receiver(post_save, sender='calendar_app.CalendarEvent')
def auto_create_reminders(sender, instance, created, **kwargs):
    # Solo eventi nuovi e non auto-generati
    if not created or instance.is_auto_generated:
        return

    now = timezone.now()
    # Promemoria: 1 giorno prima + 1 ora prima
    offsets = [timedelta(days=1), timedelta(hours=1)]
    for offset in offsets:
        remind_time = instance.start_time - offset
        if remind_time > now:
            EventReminder.objects.get_or_create(
                event=instance,
                remind_at=remind_time,
                defaults={'sent': False}
            )