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

"""
Task Celery per sincronizzazione asincrona con Google Calendar
"""
import logging
from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_event_to_google_task(self, calendar_event_id):
    """
    Sincronizza un singolo evento su Google Calendar per tutti i membri della famiglia.
    Eseguito in modo asincrono via Celery per non bloccare la response.
    """
    from calendar_app.models import CalendarEvent, GoogleCalendarToken
    from calendar_app.services.google_calendar_service import sync_event_to_google

    try:
        event = CalendarEvent.objects.select_related('family').get(id=calendar_event_id)
    except CalendarEvent.DoesNotExist:
        logger.warning(f"❌ Evento {calendar_event_id} non trovato")
        return {'success': False, 'error': 'Evento non trovato'}

    family = event.family

    # Trova tutti i membri della famiglia con Google Calendar collegato
    tokens = GoogleCalendarToken.objects.filter(
        user__family_memberships__family=family,
        is_active=True
    ).select_related('user')

    stats = {
        'event_id': calendar_event_id,
        'total_members': tokens.count(),
        'synced': 0,
        'errors': 0,
        'skipped': 0,
    }

    # ✅ MAPPATURA: ruolo → tipi di evento che deve ricevere su Google Calendar
    role_event_mapping = {
        'lawyer_a': ['legal', 'support'],
        'lawyer_b': ['legal', 'support'],
        'mediator': ['mediation'],
        'consultant': ['consulting'],
        'parent_a': None,  # None = tutti gli eventi
        'parent_b': None,  # None = tutti gli eventi
    }

    for token in tokens:
        try:
            # ✅ Verifica il ruolo dell'utente
            from families.models import FamilyMember
            member = FamilyMember.objects.filter(
                family=family,
                user=token.user
            ).first()

            if member:
                role = str(member.role).lower()
                allowed_events = role_event_mapping.get(role)

                # Se allowed_events è None, il ruolo riceve tutti gli eventi
                # Altrimenti controlla se l'evento è nella lista consentita
                if allowed_events is None or event.event_type in allowed_events:
                    result = sync_event_to_google(token.user, event)
                    if result.get('success'):
                        stats['synced'] += 1
                    else:
                        stats['errors'] += 1
                        logger.error(f"❌ Errore sync Google per {token.user.email}: {result.get('error')}")
                else:
                    stats['skipped'] += 1
                    logger.debug(f"⏭️ Evento {event.event_type} saltato per {token.user.email} (ruolo: {role})")
            else:
                # Se non è un membro della famiglia, sincronizza comunque
                result = sync_event_to_google(token.user, event)
                if result.get('success'):
                    stats['synced'] += 1
                else:
                    stats['errors'] += 1

        except Exception as e:
            stats['errors'] += 1
            logger.error(f"❌ Eccezione sync Google per {token.user.email}: {e}")

    logger.info(f"✅ Sync Google completato per evento {calendar_event_id}: {stats}")
    return {'success': True, 'stats': stats}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def delete_event_from_google_task(self, calendar_event_id):
    """
    Elimina un singolo evento da Google Calendar per tutti i membri della famiglia.
    """
    from calendar_app.models import CalendarEvent, GoogleCalendarToken
    from calendar_app.services.google_calendar_service import delete_event_from_google

    try:
        event = CalendarEvent.objects.select_related('family').get(id=calendar_event_id)
    except CalendarEvent.DoesNotExist:
        return {'success': False, 'error': 'Evento non trovato'}

    # Se non ha google_event_id, non c'è nulla da eliminare
    if not event.google_event_id:
        return {'success': True, 'message': 'Evento non presente su Google'}

    family = event.family

    tokens = GoogleCalendarToken.objects.filter(
        user__family_memberships__family=family,
        is_active=True
    ).select_related('user')

    stats = {
        'event_id': calendar_event_id,
        'total_members': tokens.count(),
        'deleted': 0,
        'errors': 0,
    }

    for token in tokens:
        try:
            result = delete_event_from_google(token.user, event)
            if result.get('success'):
                stats['deleted'] += 1
            else:
                stats['errors'] += 1
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"❌ Eccezione delete Google per {token.user.email}: {e}")

    logger.info(f"✅ Delete Google completato per evento {calendar_event_id}: {stats}")
    return {'success': True, 'stats': stats}

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_professional_event_to_google_task(self, event_id):
    """
    Sincronizza un evento professionale sul Google Calendar personale del professionista.
    """
    from calendar_app.models import ProfessionalEvent, GoogleCalendarToken
    from calendar_app.services.google_calendar_service import sync_event_to_google
    import logging

    logger = logging.getLogger(__name__)

    try:
        event = ProfessionalEvent.objects.select_related('user').get(id=event_id)
    except ProfessionalEvent.DoesNotExist:
        logger.warning(f"❌ Evento professionale {event_id} non trovato")
        return {'success': False, 'error': 'Evento non trovato'}

    # Il professionista ha solo 1 Google Calendar token (il suo)
    try:
        token = GoogleCalendarToken.objects.get(user=event.user, is_active=True)
    except GoogleCalendarToken.DoesNotExist:
        logger.info(f"⏭️ Skip sync: {event.user.email} non ha Google Calendar collegato")
        return {'success': True, 'skipped': True}

    try:
        # ✅ Controlla se evento esiste già su Google
        if event.google_event_id:
            logger.info(f"⏭️ Evento {event.id} già sincronizzato (google_event_id: {event.google_event_id})")
            return {'success': True, 'skipped': True, 'reason': 'Già sincronizzato'}

        result = sync_event_to_google(token.user, event)
        return {'success': True, 'result': result}
    except Exception as e:
        logger.error(f"❌ Errore sync Google per evento prof. {event_id}: {e}")
        return {'success': False, 'error': str(e)}