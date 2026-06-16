# notifications/tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


# ✅ A.1: Aggiunto bind=True per accedere a self.retry e max_retries per sicurezza
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_document_expirations(self):
    """
    Controlla i documenti in scadenza. Include retry automatico in caso di errore DB.
    """
    from documents.models import Document
    from notifications.services import create_notification

    try:
        today = timezone.now().date()
        start_date = today - timedelta(days=3)
        end_date = today + timedelta(days=7)

        # Ottimizzazione: select_related per evitare query N+1
        expiring_docs = Document.objects.filter(
            expiration_date__gte=start_date,
            expiration_date__lte=end_date,
            is_active=True
        ).select_related('owner', 'family')

        count = 0
        for doc in expiring_docs:
            users_to_notify = {doc.owner}

            if doc.scope == "shared":
                # Ottimizzazione: prefetch related per i membri
                users_to_notify.update([m.user for m in doc.family.members.select_related('user').all()])

            for user in users_to_notify:
                days_left = (doc.expiration_date - today).days
                title = f"🔴 Scaduto: {doc.title}" if days_left < 0 else f"⚠️ In scadenza: {doc.title}"
                message = f"Il documento '{doc.title}' è scaduto." if days_left < 0 else f"Scade tra {days_left} giorni."

                create_notification(
                    user=user,
                    notification_type="document_expiring",
                    title=title,
                    message=message,
                    target_url=f"/documents/{doc.id}/",
                    target_model="Document",
                    target_id=doc.id
                )
                count += 1

        logger.info(f"✅ [Task Expirations] Analizzati {expiring_docs.count()} documenti, generate {count} notifiche.")

    except Exception as exc:
        logger.error(f"❌ Errore nel task check_document_expirations: {exc}")
        # ✅ Retry esponenziale o fisso in caso di errore (es. DB down)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_pending_agreements(self):
    """
    Controlla gli accordi in attesa di firma.
    """
    from documents.models import MediationAgreement
    from notifications.services import create_notification

    try:
        threshold_date = timezone.now() - timedelta(days=3)

        pending_agreements = MediationAgreement.objects.filter(
            status__in=['review', 'signing'],
            updated_at__lte=threshold_date
        ).select_related('family', 'mediator')

        count = 0
        for agreement in pending_agreements:
            users_to_notify = set()
            if agreement.mediator:
                users_to_notify.add(agreement.mediator)
            users_to_notify.update([m.user for m in agreement.family.members.select_related('user').all()])

            days_pending = (timezone.now() - agreement.updated_at).days

            for user in users_to_notify:
                create_notification(
                    user=user,
                    notification_type="agreement_pending",
                    title=f"✍️ Accordo in attesa: {agreement.title}",
                    message=f"L'accordo è in attesa da {days_pending} giorni.",
                    target_url=f"/mediation/agreements/{agreement.id}/",
                    target_model="MediationAgreement",
                    target_id=agreement.id
                )
                count += 1

        logger.info(f"✅ [Task Agreements] Analizzati {pending_agreements.count()} accordi, generate {count} notifiche.")

    except Exception as exc:
        logger.error(f"❌ Errore nel task check_pending_agreements: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_imminent_events(self):
    """
    Controlla gli eventi imminenti (prossime 24h).
    """
    from calendar_app.models import CalendarEvent
    from notifications.services import create_notification

    try:
        now = timezone.now()
        horizon = now + timedelta(hours=24)

        imminent_events = CalendarEvent.objects.filter(
            start_time__gte=now,
            start_time__lte=horizon,
            is_active=True
        ).select_related('family', 'created_by')

        count = 0
        for event in imminent_events:
            users_to_notify = {event.created_by}

            if event.is_shared:
                users_to_notify.update([m.user for m in event.family.members.select_related('user').all()])

            for user in users_to_notify:
                create_notification(
                    user=user,
                    notification_type="event_imminent",
                    title=f"⏰ Evento imminente: {event.title}",
                    message=f"L'evento inizierà il {event.start_time.strftime('%d/%m/%Y alle %H:%M')}.",
                    target_url=f"/calendar/event/{event.id}/",
                    target_model="CalendarEvent",
                    target_id=event.id
                )
                count += 1

        logger.info(f"✅ [Task Events] Analizzati {imminent_events.count()} eventi, generate {count} notifiche.")

    except Exception as exc:
        logger.error(f"❌ Errore nel task check_imminent_events: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))