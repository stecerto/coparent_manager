# families/signals.py
import logging
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal

logger = logging.getLogger(__name__)

# Segnale personalizzato per l'attivazione utente
user_activated = Signal()

User = get_user_model()

@receiver(post_save, sender=User)
def handle_user_activation(sender, instance, created, **kwargs):
    """
    Quando un utente viene salvato, controlla se è stato appena attivato.
    Se sì, invia il segnale user_activated.
    """
    # Controlla se l'utente è attivo e non è appena stato creato
    # (vogliamo catturare il momento in cui is_active diventa True)
    if not created and instance.is_active:
        # Verifica se è la prima volta che viene attivato
        # (possiamo usare un campo o controllare lo stato precedente)
        # Per semplicità, inviamo il segnale ogni volta che viene salvato ed è attivo
        # La logica di idempotenza sarà nel handler
        logger.info(f"📡 Utente {instance.email} salvato e attivo. Invio segnale user_activated.")
        user_activated.send(sender=sender, user=instance)