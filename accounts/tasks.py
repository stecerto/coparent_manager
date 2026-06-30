from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task
def cleanup_inactive_users_task():
    """
    Elimina account inattivi (non attivati) dopo 15 giorni.
    Eseguito automaticamente da Celery Beat ogni giorno alle 3:00.
    """
    days = 15
    cutoff_date = timezone.now() - timedelta(days=days)

    # Trova utenti inattivi più vecchi di 15 giorni
    inactive_users = User.objects.filter(
        is_active=False,
        date_joined__lt=cutoff_date
    )

    count = inactive_users.count()

    if count == 0:
        logger.info("✅ Cleanup: nessun account inattivo da eliminare")
        return 0

    logger.info(f"🔍 Cleanup: trovati {count} account inattivi da eliminare")

    # Elimina profili, inviti e utenti
    deleted_count = 0
    for user in inactive_users:
        try:
            # Elimina profilo se esiste
            if hasattr(user, 'userprofile'):
                user.userprofile.delete()

            # Elimina inviti pendenti
            if hasattr(user, 'sent_invitations'):
                user.sent_invitations.filter(status='pending').delete()

            # Elimina utente
            user_email = user.email
            user.delete()
            deleted_count += 1
            logger.info(f"🗑️ Eliminato account inattivo: {user_email}")

        except Exception as e:
            logger.error(f"❌ Errore eliminazione utente {user.email}: {e}")

    logger.info(f"✅ Cleanup completato: eliminati {deleted_count} account inattivi")
    return deleted_count