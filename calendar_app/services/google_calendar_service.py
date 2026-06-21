"""
Servizio per integrazione Google Calendar
"""
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_google_credentials(user):
    """Ottiene credenziali Google per l'utente"""
    try:
        from google.oauth2.credentials import Credentials
        from calendar_app.models import GoogleCalendarToken

        token_obj = GoogleCalendarToken.objects.get(user=user, is_active=True)

        credentials = Credentials(
            token=token_obj.access_token,
            refresh_token=token_obj.refresh_token,
            token_uri=token_obj.token_uri,
            client_id=token_obj.client_id,
            client_secret=token_obj.client_secret,
            scopes=token_obj.scopes.split()
        )

        # Aggiorna token se scaduto
        if token_obj.is_expired:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())

            # Salva nuovi token
            token_obj.access_token = credentials.token
            if credentials.expiry:
                token_obj.expiry = credentials.expiry
            token_obj.save()

        return credentials

    except GoogleCalendarToken.DoesNotExist:
        logger.warning(f"Utente {user.email} non ha token Google Calendar")
        return None
    except Exception as e:
        logger.error(f"Errore recupero credenziali Google: {e}")
        return None


def build_google_calendar_service(credentials):
    """Costruisce il servizio Google Calendar"""
    try:
        from googleapiclient.discovery import build

        service = build('calendar', 'v3', credentials=credentials)
        return service

    except Exception as e:
        logger.error(f"Errore build servizio Google Calendar: {e}")
        return None


def sync_event_to_google(user, calendar_event):
    """
    Sincronizza un evento CoParent → Google Calendar

    Args:
        user: Utente che ha collegato il calendario
        calendar_event: Istanza CalendarEvent

    Returns:
        dict: Risultato della sincronizzazione
    """
    credentials = get_google_credentials(user)
    if not credentials:
        return {'success': False, 'error': 'Credenziali non valide'}

    service = build_google_calendar_service(credentials)
    if not service:
        return {'success': False, 'error': 'Errore servizio Google'}

    try:
        # Prepara evento Google
        event = {
            'summary': calendar_event.title,
            'description': calendar_event.description or '',
            'start': {
                'dateTime': calendar_event.start_time.isoformat(),
                'timeZone': 'Europe/Rome',
            },
            'end': {
                'dateTime': calendar_event.end_time.isoformat(),
                'timeZone': 'Europe/Rome',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }

        # Controlla se evento esiste già su Google
        if calendar_event.google_event_id:
            # Aggiorna evento esistente
            updated_event = service.events().update(
                calendarId='primary',
                eventId=calendar_event.google_event_id,
                body=event
            ).execute()

            logger.info(f"✅ Evento Google aggiornato: {updated_event.get('id')}")
            return {'success': True, 'google_event_id': updated_event.get('id')}

        else:
            # Crea nuovo evento
            created_event = service.events().insert(
                calendarId='primary',
                body=event
            ).execute()

            # Salva google_event_id nel modello
            calendar_event.google_event_id = created_event.get('id')
            calendar_event.save(update_fields=['google_event_id'])

            logger.info(f"✅ Evento Google creato: {created_event.get('id')}")
            return {'success': True, 'google_event_id': created_event.get('id')}

    except Exception as e:
        logger.error(f"❌ Errore sync evento Google: {e}")
        return {'success': False, 'error': str(e)}


def delete_event_from_google(user, calendar_event):
    """Elimina evento da Google Calendar"""
    if not calendar_event.google_event_id:
        return {'success': True, 'message': 'Evento non presente su Google'}

    credentials = get_google_credentials(user)
    if not credentials:
        return {'success': False, 'error': 'Credenziali non valide'}

    service = build_google_calendar_service(credentials)
    if not service:
        return {'success': False, 'error': 'Errore servizio Google'}

    try:
        service.events().delete(
            calendarId='primary',
            eventId=calendar_event.google_event_id
        ).execute()

        logger.info(f"✅ Evento Google eliminato: {calendar_event.google_event_id}")
        return {'success': True}

    except Exception as e:
        logger.error(f"❌ Errore eliminazione evento Google: {e}")
        return {'success': False, 'error': str(e)}


def sync_all_events_to_google(user, family):
    """
    Sincronizza TUTTI gli eventi della famiglia su Google Calendar

    Returns:
        dict: Statistiche sincronizzazione
    """
    from calendar_app.models import CalendarEvent

    credentials = get_google_credentials(user)
    if not credentials:
        return {'success': False, 'error': 'Credenziali non valide'}

    service = build_google_calendar_service(credentials)
    if not service:
        return {'success': False, 'error': 'Errore servizio Google'}

    events = CalendarEvent.objects.filter(
        family=family,
        is_active=True
    )

    stats = {
        'total': events.count(),
        'synced': 0,
        'errors': 0,
        'skipped': 0
    }

    for event in events:
        result = sync_event_to_google(user, event)

        if result['success']:
            stats['synced'] += 1
        else:
            stats['errors'] += 1
            logger.error(f"Errore sync evento {event.id}: {result.get('error')}")

    # Aggiorna last_sync_at
    from calendar_app.models import GoogleCalendarToken
    GoogleCalendarToken.objects.filter(user=user).update(last_sync_at=timezone.now())

    logger.info(f"✅ Sync completato: {stats}")
    return {'success': True, 'stats': stats}


def cleanup_future_events_from_google(user, family, end_date, source_filter=None):
    """
    Elimina da Google Calendar gli eventi FUTURI generati dall'app.

    Args:
        user: Utente connesso a Google
        family: Famiglia di riferimento
        end_date: Data limite (eventi dopo questa data vengono eliminati)
        source_filter: Filtro opzionale per source (es. 'child_support', 'spouse_support')

    Returns:
        dict: Statistiche eliminazione
    """
    from calendar_app.models import CalendarEvent

    credentials = get_google_credentials(user)
    if not credentials:
        return {'success': False, 'error': 'Credenziali non valide'}

    service = build_google_calendar_service(credentials)
    if not service:
        return {'success': False, 'error': 'Errore servizio Google'}

    # ✅ FILTRO CRITICO: Solo eventi auto-generati CON google_event_id
    # Questo garantisce di NON toccare eventi creati manualmente dall'utente
    events_to_delete = CalendarEvent.objects.filter(
        family=family,
        is_active=True,
        is_auto_generated=True,  # ✅ Solo eventi generati dall'app
        google_event_id__isnull=False,  # ✅ Solo eventi sincronizzati
        start_time__date__gt=end_date  # ✅ Solo eventi futuri
    )

    # Filtro opzionale per source
    if source_filter:
        events_to_delete = events_to_delete.filter(source=source_filter)

    stats = {
        'total': events_to_delete.count(),
        'deleted': 0,
        'errors': 0
    }

    for event in events_to_delete:
        try:
            # Elimina da Google
            service.events().delete(
                calendarId='primary',
                eventId=event.google_event_id
            ).execute()

            # Pulisci google_event_id (l'evento rimane in CoParent ma non più su Google)
            event.google_event_id = None
            event.save(update_fields=['google_event_id'])

            stats['deleted'] += 1
            logger.info(f"✅ Evento Google eliminato: {event.title} ({event.google_event_id})")

        except Exception as e:
            stats['errors'] += 1
            logger.error(f"❌ Errore eliminazione evento Google {event.id}: {e}")

    logger.info(f"✅ Cleanup completato: {stats}")
    return {'success': True, 'stats': stats}