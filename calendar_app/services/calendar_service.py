import logging
from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from calendar_app.models import CalendarEvent, EventReminder
from core.choices import RoleChoices
from families.models import FamilyMember
from notifications.services import create_notification

logger = logging.getLogger(__name__)

"""
Servizio per generazione eventi calendario mantenimento figli.
Simile al funzionamento del mantenimento coniuge.
"""
import calendar
from datetime import datetime, date
from django.utils import timezone
from dateutil.relativedelta import relativedelta


def generate_child_support_calendar_events(support):
    """
    Genera eventi mensili di mantenimento figli per l'anno in corso.
    Se il mantenimento ha end_date, genera solo fino a quella data.
    """
    from calendar_app.models import CalendarEvent

    child = support.child
    family = support.family

    if not family:
        return 0

    child_name = f"{child.name} {child.surname}"
    title = f"💶 Mantenimento: {child_name}"

    # Determina data inizio e fine
    current_date = support.start_date.replace(day=1)  # Primo giorno del mese

    # Fine: end_date se esiste, altrimenti 12 mesi dalla start_date
    if support.end_date:
        end_date = support.end_date
    else:
        end_date = support.start_date + relativedelta(months=12)

    # Genera solo per i prossimi 12 mesi per non appesantire il DB
    horizon = date.today() + relativedelta(months=12)
    limit_date = min(end_date, horizon)

    # Giorno pagamento: di default il 5 del mese
    payment_day = 5

    created_count = 0
    while current_date <= limit_date:
        # Adatta il giorno al mese corrente
        max_day = calendar.monthrange(current_date.year, current_date.month)[1]
        day = min(payment_day, max_day)

        event_date = current_date.replace(day=day)
        start_dt = timezone.make_aware(datetime.combine(event_date, datetime.min.time().replace(hour=9)))
        end_dt = timezone.make_aware(datetime.combine(event_date, datetime.min.time().replace(hour=18)))

        # Evita duplicati
        if not CalendarEvent.objects.filter(
                family=family,
                source="child_support",
                linked_id=support.id,
                start_time__year=event_date.year,
                start_time__month=event_date.month
        ).exists():
            # Determina chi versa
            if support.payer_role == 'parent_a':
                payer_label = "Genitore A → Genitore B"
            else:
                payer_label = "Genitore B → Genitore A"

            new_event = CalendarEvent.objects.create(
                family=family,
                title=title,
                description=f"Mantenimento mensile per {child_name}\nImporto: €{support.amount}\n{payer_label}",
                start_time=start_dt,
                end_time=end_dt,
                event_type="support",
                is_auto_generated=True,
                created_by=support.child.modified_by or family.members.first().user,
                is_shared=True,
                source="child_support",
                linked_id=support.id,
            )
            created_count += 1

            # ✅ AVVIA SYNC ASINCRONO CON GOOGLE CALENDAR
            try:
                from calendar_app.tasks import sync_event_to_google_task
                sync_event_to_google_task.delay(new_event.id)
                print(f"  📅 Task Celery avviato per evento {new_event.id}")
            except Exception as e:
                print(f"  ⚠️ Errore avvio task Celery per evento {new_event.id}: {e}")

        current_date += relativedelta(months=1)

    return created_count


def cleanup_child_support_calendar_events(support):
    """
    Elimina eventi calendario dopo la data di fine mantenimento.
    """
    from calendar_app.models import CalendarEvent

    family = support.family
    if not family:
        return 0

    # Se end_date è None, non eliminare nulla
    if not support.end_date:
        return 0

    # Elimina eventi successivi a end_date
    deleted_count, _ = CalendarEvent.objects.filter(
        family=family,
        source="child_support",
        linked_id=support.id,
        start_time__date__gt=support.end_date
    ).delete()

    return deleted_count


def create_event(family, created_by, title, start_time, end_time, **kwargs):
    """
    Crea un evento calendario.
    ✅ ARCHITETTURA AGGIORNATA: Non crea più spese automaticamente.
    Le spese si gestiscono esclusivamente dall'app Expenses.
    """
    # Crea l'evento
    event = CalendarEvent.objects.create(
        family=family,
        created_by=created_by,
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=kwargs.get("description", ""),
        event_type=kwargs.get("event_type", "other"),
        is_shared=kwargs.get("is_shared", True),
        source=kwargs.get("source", "manual"),
    )

    # Gestione figli (ManyToMany)
    children = kwargs.get("children")
    if children:
        event.children.set(children)

    # ✅ NOTIFICHE FILTRATE PER RUOLO E TIPO EVENTO
    role_event_mapping = {
        'lawyer_a': ['legal', 'support', 'mediation', 'consulting'],
        'lawyer_b': ['legal', 'support', 'mediation', 'consulting'],
        'mediator': ['mediation'],
        'consultant': ['consulting'],
        'parent_a': None,
        'parent_b': None,
    }

    members = FamilyMember.objects.filter(
        family=family,
        user__is_active=True
    ).select_related('user')

    for member in members:
        role = str(member.role).lower()
        allowed_events = role_event_mapping.get(role)

        if allowed_events is None or event.event_type in allowed_events:
            try:
                create_notification(
                    user=member.user,
                    notification_type="calendar_event_created",
                    title=f"📅 Nuovo evento: {title}",
                    message=f"È stato creato un nuovo evento '{title}' per il {start_time.strftime('%d/%m/%Y')} nella famiglia {family.name}.",
                    target_url=f"/calendar/events/",
                    target_model="CalendarEvent",
                    target_id=event.id,
                    metadata={"event_type": event.event_type}
                )
            except Exception as e:
                logger.error(f"Errore invio notifica evento a {member.user.email}: {e}")

    # ✅ AVVIA SYNC ASINCRONO CON GOOGLE CALENDAR
    try:
        from calendar_app.tasks import sync_event_to_google_task
        sync_event_to_google_task.delay(event.id)
        logger.info(f"📅 Task Celery avviato per sync Google evento {event.id}")
    except Exception as e:
        logger.error(f"⚠️ Errore avvio task Celery per evento {event.id}: {e}")

    return event


def update_event(event, user, data):
    """
    Crea nuova versione e archivia la precedente.
    ✅ ARCHITETTURA AGGIORNATA: Non aggiorna più le spese collegate.
    """
    # Archivia evento precedente
    event.is_active = False
    event.archived_at = timezone.now()
    event.archived_by = user
    event.save()

    # Crea nuova versione
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

    )

    # Gestione figli
    children = data.get("children")
    if children is not None:
        new_event.children.set(list(children))
    else:
        new_event.children.set(event.children.all())
    # ✅ AVVIA SYNC ASINCRONO CON GOOGLE CALENDAR
    try:
        from calendar_app.tasks import sync_event_to_google_task
        sync_event_to_google_task.delay(new_event.id)
        logger.info(f"📅 Task Celery avviato per sync Google evento {new_event.id}")
    except Exception as e:
        logger.error(f"⚠️ Errore avvio task Celery per evento {new_event.id}: {e}")

    return new_event




def get_family_events(family):
    return CalendarEvent.objects.filter(
        family=family,
        is_active=True
    ).order_by("start_time")


# ✅ Usa la stringa per evitare AppRegistryNotReady
@receiver(post_save, sender='calendar_app.CalendarEvent')
def auto_create_reminders(sender, instance, created, **kwargs):
    """Crea automaticamente i promemoria per i nuovi eventi."""
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