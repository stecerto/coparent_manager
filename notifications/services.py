# notifications/services.py
import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from .models import Notification
import urllib.parse

logger = logging.getLogger(__name__)


def create_notification(user, notification_type, title, message, target_url=None, target_model=None, target_id=None,
                        metadata=None, send_email=True):
    """
    Crea notifica in-app e invia email opzionale.
    Idempotente: controlla duplicati negli ultimi 5 minuti.
    """
    from django.utils import timezone
    from datetime import timedelta

    # ✅ Evita spam: non creare duplicati dello stesso tipo negli ultimi 5 min
    recent = Notification.objects.filter(
        user=user,
        notification_type=notification_type,
        target_model=target_model,
        target_id=target_id,
        created_at__gte=timezone.now() - timedelta(minutes=5)
    ).exists()

    if recent:
        logger.debug(f"Skip duplicate notification: {notification_type} for {user.email}")
        return None

    notification = Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        target_url=target_url,
        target_model=target_model,
        target_id=target_id,
        metadata=metadata or {}
    )

    # 📧 Invia email se richiesto e l'utente ha email valida
    if send_email and user.email and not notification.is_sent_email:
        try:
            subject = f"🔔 {title}"
            html_message = render_to_string("notifications/email_template.html", {
                "user": user,
                "notification": notification,
                "site_url": getattr(settings, "SITE_URL", "http://localhost:8000")
            })

            send_mail(
                subject=subject,
                message=message,  # fallback plain text
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            notification.is_sent_email = True
            notification.sent_at = timezone.now()
            notification.save(update_fields=["is_sent_email", "sent_at"])
            import logging
            logging.getLogger(__name__).info(f"✅ Email inviata a {user.email}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"❌ Errore email notifica {notification.id}: {e}", exc_info=True)

    return notification

def get_whatsapp_link(phone_number_obj, message_text=""):
    """Genera link wa.me da PhoneNumberField"""
    if not phone_number_obj:
        return None
    # str() converte PhoneNumber in formato E.164: "+393331234567"
    phone_str = str(phone_number_obj).replace(" ", "").replace("-", "")
    encoded_msg = urllib.parse.quote(message_text[:1000])
    return f"https://wa.me/{phone_str}?text={encoded_msg}"