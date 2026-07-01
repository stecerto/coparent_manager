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

        activation_link = (
            f"{request.scheme}://{request.get_host()}/accounts/activate/?{params}"
        )

        context = {
            "user": user,
            "activation_link": activation_link,
            "site_name": getattr(settings, "SITE_NAME", "CoParentManager"),
            "is_resend": subject_prefix != ""
        }

        html_content = render_to_string("emails/activation_email.html", context)
        text_content = strip_tags(html_content)

        subject = f"{subject_prefix}Attiva il tuo account - CoParentManager"
        message = f"Ciao {user.first_name or user.email},\n\nClicca sul link per attivare il tuo account:\n{activation_link}\n\nSe non hai richiesto questa registrazione, ignora questa email."

        # ✅ SOSTITUISCI send_mail() CON QUESTA CHIAMATA API
        return send_mailjet_api(
            to_email=user.email,
            to_name=f"{user.first_name} {user.last_name}".strip() or user.email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    except Exception as e:
        logger.error(f"❌ Errore invio attivazione a {user.email}: {e}")
        if settings.DEBUG:
            import traceback
            traceback.print_exc()
        return False


# ✅ AGGIUNGI QUESTA FUNZIONE
def send_mailjet_api(to_email, to_name, subject, html_content, text_content=None):
    """
    Invia email usando Mailjet API v3.1 (non SMTP).
    Più affidabile su Render perché usa HTTPS invece di SMTP.
    """
    try:
        import requests
        import os

        api_key = os.getenv('MAILJET_API_KEY')
        api_secret = os.getenv('MAILJET_SECRET_KEY')
        from_email = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@coparentmanager.com')

        if not api_key or not api_secret:
            logger.error("❌ Credenziali Mailjet mancanti")
            return False

        url = "https://api.mailjet.com/v3.1/send"

        payload = {
            "Messages": [{
                "From": {
                    "Email": from_email,
                    "Name": "CoParentManager"
                },
                "To": [{
                    "Email": to_email,
                    "Name": to_name
                }],
                "Subject": subject,
                "HTMLPart": html_content,
            }]
        }

        if text_content:
            payload["Messages"][0]["TextPart"] = text_content

        response = requests.post(
            url,
            auth=(api_key, api_secret),
            json=payload,
            timeout=10  # ← Timeout 10 secondi (non infinito come SMTP)
        )

        if response.status_code == 200:
            logger.info(f"📧 Email inviata con successo a {to_email}")
            return True
        else:
            logger.error(f"❌ Errore Mailjet API: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"❌ Errore invio email Mailjet: {e}", exc_info=True)
        return False