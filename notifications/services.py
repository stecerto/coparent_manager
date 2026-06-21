# notifications/services.py
import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from .models import Notification
import urllib.parse

logger = logging.getLogger(__name__)


def create_notification(
        user,
        notification_type,
        title,
        message,
        target_url=None,
        target_model=None,
        target_id=None,
        metadata=None,
        ):
    """
    Crea notifica in-app e invia email opzionale.
    Idempotente: controlla duplicati negli ultimi 5 minuti.
    """
    from django.utils import timezone
    from datetime import timedelta

    # ✅ Aumenta a 1 ora per evitare duplicati
    recent = Notification.objects.filter(
        user=user,
        notification_type=notification_type,
        target_model=target_model,
        target_id=target_id,
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).exists()

    if recent:
        return None

    notification = Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        target_url=target_url,
        target_model=target_model,
        target_id=target_id,
        metadata=metadata or {},
        is_read = False,
        created_at = timezone.now()
    )
    return notification

def get_whatsapp_link(phone_number_obj, message_text=""):
    """Genera link wa.me da PhoneNumberField"""
    if not phone_number_obj:
        return None
    # str() converte PhoneNumber in formato E.164: "+393331234567"
    phone_str = str(phone_number_obj).replace(" ", "").replace("-", "")
    encoded_msg = urllib.parse.quote(message_text[:1000])
    return f"https://wa.me/{phone_str}?text={encoded_msg}"