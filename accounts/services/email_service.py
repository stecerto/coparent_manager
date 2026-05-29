# accounts/email_service.py
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.defaultfilters import safe
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode

from core.email_utils import send_html_email

logger = logging.getLogger(__name__)


# accounts/email_service.py

def send_activation_email(request, user, subject_prefix=""):
    """
    Invia email di attivazione account con link sicuro.

    Args:
        request: Django request per build_absolute_uri
        user: User instance da attivare
        subject_prefix: Prefisso opzionale per l'oggetto (es. "Nuovo ")

    Returns:
        bool: True se inviata, False altrimenti
    """
    if not user or not hasattr(user, 'email') or not user.email:
        logger.error(f"❌ Impossibile inviare email: user={user}")
        return False

    email = user.email.strip().lower()
    if '@' not in email:
        logger.error(f"❌ Email non valida: '{email}'")
        return False

    try:
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        params = urlencode({
            "uidb64": uidb64,
            "token": token,
        })


        # ✅ Link coerente con la view di attivazione
        activation_link = (
            f"{request.scheme}://{request.get_host()}/accounts/activate/?{params}"

        )

        context = {
            "user": user,
            "activation_link": activation_link,
            "site_name": getattr(settings, "SITE_NAME", "CoParentManager"),
            "is_resend": subject_prefix != ""  # utile nel template se vuoi mostrare un messaggio diverso
        }

        html_content = render_to_string("emails/activation_email.html", context)
        text_content = strip_tags(html_content)

        send_mail(
            subject=f"{subject_prefix}Attiva il tuo account - CoParentManager",
            message=f"Ciao {user.first_name or user.email},\n\n"
                    f"Clicca sul link per attivare il tuo account:\n{activation_link}\n\n"
                    f"Se non hai richiesto questa registrazione, ignora questa email.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,  # ✅ Corretto: html_content, non text_content!
            fail_silently=False
        )
        logger.info(f"📧 Email di attivazione {subject_prefix.lower().strip()}inviata a {user.email}")
        return True

    except Exception as e:
        logger.error(f"❌ Errore invio attivazione a {user.email}: {e}")
        if settings.DEBUG:
            import traceback
            traceback.print_exc()
        return False