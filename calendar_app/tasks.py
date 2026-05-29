# calendar_app/tasks.py
import logging
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import EventReminder, CalendarEvent

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_event_reminder(self):
    """
    Invia email per i promemodi scaduti non ancora inviati.
    Gira ogni 5 minuti tramite Celery Beat.
    """
    now = timezone.now()
    due_reminders = EventReminder.objects.filter(
        sent=False,
        remind_at__lte=now,
        event__is_active=True
    ).select_related('event', 'event__family', 'event__created_by')

    if not due_reminders.exists():
        logger.debug("Nessun promemodo da inviare.")
        return 0

    success_count = 0
    for reminder in due_reminders:
        try:
            event = reminder.event
            family = event.family

            # 📧 Destinatari: membri attivi della famiglia con email valida
            recipients = [
                m.user.email
                for m in family.members.filter(user__is_active=True, user__email__isnull=False)
            ]
            if not recipients:
                logger.warning(f"Skip reminder {reminder.id}: nessun destinatario valido")
                reminder.sent = True
                reminder.save(update_fields=['sent'])
                continue

            subject = f"📅 Promemoria: {event.title}"
            message = (
                f"Ciao,\n\n"
                f"Questo è un promemoria per l'evento:\n"
                f"📌 {event.title}\n"
                f"📅 Inizio: {event.start_time.strftime('%d/%m/%Y %H:%M')}\n"
                f"📝 {event.description or 'Nessuna descrizione'}\n\n"
                f"Vedi tutti i dettagli nella piattaforma: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/calendar/"
            )

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=False,
            )

            reminder.sent = True
            reminder.save(update_fields=['sent'])
            success_count += 1

        except Exception as e:
            logger.error(f"Errore invio reminder {reminder.id}: {e}", exc_info=True)
            # Retry automatico grazie a max_retries=3

    logger.info(f"✅ Promemodi inviati: {success_count}")
    return success_count