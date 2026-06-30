#!/usr/bin/env python
"""
Script per cleanup account inattivi.
Eseguibile manualmente o via cron su Render.

Uso:
    python scripts/cleanup_inactive.py
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

User = get_user_model()


def cleanup_inactive_users(days=15):
    """Elimina account inattivi più vecchi di N giorni."""
    cutoff_date = timezone.now() - timedelta(days=days)

    inactive_users = User.objects.filter(
        is_active=False,
        date_joined__lt=cutoff_date
    )

    count = inactive_users.count()

    if count == 0:
        logger.info(f"✅ Nessun account inattivo da eliminare (>{days} giorni)")
        return 0

    logger.info(f"🔍 Trovati {count} account inattivi da eliminare")

    deleted_count = 0
    for user in inactive_users:
        try:
            if hasattr(user, 'userprofile'):
                user.userprofile.delete()

            if hasattr(user, 'sent_invitations'):
                user.sent_invitations.filter(status='pending').delete()

            user_email = user.email
            user.delete()
            deleted_count += 1
            logger.info(f"🗑️ Eliminato: {user_email}")

        except Exception as e:
            logger.error(f"❌ Errore eliminazione {user.email}: {e}")

    logger.info(f"✅ Completato: eliminati {deleted_count} account")
    return deleted_count


if __name__ == '__main__':
    cleanup_inactive_users(days=15)

    '''
    Dalla Shell di Render (se hai piano a pagamento):
    
    python scripts/cleanup_inactive.py
    
    
    
    Automazione con Cron Job Render
        Se hai piano a pagamento ($7/mese), crea un Cron Job su Render:
        Dashboard Render → Cron Jobs → Create Cron Job
        Name: cleanup-inactive-users
        Schedule: 0 3 * * * (ogni giorno alle 3:00)
        Command: python scripts/cleanup_inactive.py
    '''