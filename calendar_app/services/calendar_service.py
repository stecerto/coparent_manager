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

# ❌ RIMOSSO: from expenses.models import Expense, ExpenseCategory
# Il calendario non deve più sapere nulla delle spese.


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
        # ❌ RIMOSSO: expense_category=kwargs.get("expense_category"),
    )

    # ❌ RIMOSSO: L'intero blocco "if expense_category and amount:"
    # che creava l'oggetto Expense e lo collegava a event.linked_expense.

    # Gestione figli (ManyToMany)
    children = kwargs.get("children")
    if children:
        event.children.set(children)

    professional_roles = [
        RoleChoices.LAWYER_A, RoleChoices.LAWYER_B,
        RoleChoices.MEDIATOR, RoleChoices.CONSULTANT
    ]

    # Trova tutti i membri della famiglia che sono professionisti
    pros = FamilyMember.objects.filter(family=family, role__in=professional_roles).select_related('user')

    for pro in pros:
        try:
            create_notification(
                user=pro.user,
                notification_type="calendar_event_created",
                title=f"📅 Nuovo evento: {title}",
                message=f"È stato creato un nuovo evento '{title}' per il {start_time.strftime('%d/%m/%Y')} nella famiglia {family.name}.",
                target_url=f"/calendar/events/",
                target_model="CalendarEvent",
                target_id=event.id,
                metadata={"event_type": event.event_type}
            )
        except Exception as e:
            logger.error(f"Errore invio notifica evento a {pro.user.email}: {e}")

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
        # ❌ RIMOSSO: expense_category=data.get("expense_category", event.expense_category),
    )

    # ❌ RIMOSSO: L'intero blocco "if event.linked_expense:"
    # che aggiornava importo e categoria della spesa collegata.

    # Gestione figli
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