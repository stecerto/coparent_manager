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

# calendar_app/services/calendar_service.py
from django.utils import timezone
from calendar_app.models import CalendarEvent, EventReminder
from expenses.models import Expense, ExpenseCategory


def create_event(family, created_by, title, start_time, end_time, **kwargs):
    """
    Crea un evento calendario.
    Se expense_category e amount sono forniti, crea automaticamente una Expense.
    """
    expense_category = kwargs.get("expense_category")
    amount = kwargs.get("amount")

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
        expense_category=expense_category,  # ✅ Link a categoria
    )

    # ✅ Se c'è categoria e importo, crea automaticamente la spesa
    if expense_category and amount:
        from decimal import Decimal

        # Crea la spesa collegata
        expense = Expense.objects.create(
            family=family,
            created_by=created_by,
            category=expense_category,
            description=f"{title}: {kwargs.get('description', '')}",
            amount=Decimal(str(amount)),
            expense_date=start_time.date(),
            status='pending',  # Stato in attesa di approvazione
            expense_type='shared',
        )

        # Collega l'evento alla spesa
        event.linked_expense = expense
        event.save(update_fields=['linked_expense'])

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"✅ Spesa automatica creata: ID {expense.id} per evento {event.id}")

    # Gestione figli (ManyToMany)
    children = kwargs.get("children")
    if children:
        event.children.set(children)

    return event


def update_event(event, user, data):
    """
    Crea nuova versione e archivia la precedente.
    Se amount cambia, aggiorna la spesa collegata.
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
        expense_category=data.get("expense_category", event.expense_category),
    )

    # ✅ Se c'è una spesa collegata, aggiornala se necessario
    if event.linked_expense:
        new_amount = data.get("amount")
        new_category = data.get("expense_category", event.expense_category)

        # Aggiorna spesa se importo o categoria sono cambiati
        if new_amount or new_category != event.expense_category:
            expense = event.linked_expense
            if new_amount:
                from decimal import Decimal
                expense.amount = Decimal(str(new_amount))
            if new_category:
                expense.category = new_category
            expense.description = f"{new_event.title}: {new_event.description}"
            expense.save()

        # Collega la stessa spesa al nuovo evento
        new_event.linked_expense = event.linked_expense
        new_event.save(update_fields=['linked_expense'])

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