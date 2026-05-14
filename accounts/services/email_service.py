# accounts/email_service.py
import logging
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def send_activation_email(request, user):
    """
    Invia email di attivazione account con link sicuro.
    Usa query parameters per compatibilità con la view activate_account.
    """
    # Genera token di attivazione
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    # ✅ Costruisci link con query parameters (coerente con la view)
    activation_link = (
        f"{request.scheme}://{request.get_host()}/accounts/activate/"
        f"?uidb64={uidb64}&token={token}"
    )

    # Contesto per il template email
    context = {
        "user": user,
        "activation_link": activation_link,
        "site_name": getattr(settings, "SITE_NAME", "CoParentManager"),
    }

    html_message = render_to_string("emails/activation_email.html", context)

    try:
        send_mail(
            subject="✅ Attiva il tuo account - CoParentManager",
            message=f"Ciao {user.first_name or user.email},\n\n"
                    f"Clicca sul link per attivare il tuo account:\n{activation_link}\n\n"
                    f"Se non hai richiesto questa registrazione, ignora questa email.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"📧 Email di attivazione inviata a {user.email}")
    except Exception as e:
        logger.error(f"❌ Errore invio email di attivazione a {user.email}: {e}")
        # In produzione, potresti voler raise o notificare un servizio di monitoring
