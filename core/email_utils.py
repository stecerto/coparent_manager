# core/email_utils.py

import logging
import os
import requests
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)


def send_html_email(
        subject,
        recipient_list,
        template_name,
        context,
        from_email=None,
        fail_silently=False,
        log_prefix="Email"
):
    """
    Invia email HTML usando Mailjet API (non SMTP).
    Mantiene la stessa signature per retrocompatibilità.

    Args:
        subject: Oggetto email
        recipient_list: Lista di email destinatari
        template_name: Path template HTML
        context: Dizionario contesto per il template
        from_email: Email mittente (opzionale)
        fail_silently: Se True, non solleva eccezioni
        log_prefix: Prefisso per i log

    Returns:
        bool: True se inviata con successo
    """
    try:
        # Renderizza template HTML
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)

        # Email mittente
        from_email = from_email or settings.DEFAULT_FROM_EMAIL

        # ✅ Usa Mailjet API invece di SMTP
        return send_mailjet_api(
            subject=subject,
            recipient_list=recipient_list,
            html_content=html_content,
            text_content=text_content,
            from_email=from_email,
            fail_silently=fail_silently,
            log_prefix=log_prefix
        )

    except Exception as e:
        logger.error(f"❌ Errore invio {log_prefix}: {e}")

        if settings.DEBUG:
            import traceback
            traceback.print_exc()

        if not fail_silently:
            raise

        return False


def send_mailjet_api(
        subject,
        recipient_list,
        html_content,
        text_content=None,
        from_email=None,
        from_name="CoParentManager",
        fail_silently=False,
        log_prefix="Email"
):
    """
    Invia email usando Mailjet API v3.1 (non SMTP).
    Più affidabile su Render perché usa HTTPS invece di SMTP.

    Args:
        subject: Oggetto email
        recipient_list: Lista di email destinatari
        html_content: Contenuto HTML
        text_content: Contenuto testo (opzionale)
        from_email: Email mittente
        from_name: Nome mittente
        fail_silently: Se True, non solleva eccezioni
        log_prefix: Prefisso per i log

    Returns:
        bool: True se inviata con successo
    """
    try:
        # Recupera credenziali Mailjet
        api_key = os.getenv('MAILJET_API_KEY')
        api_secret = os.getenv('MAILJET_SECRET_KEY')
        from_email = from_email or os.getenv('DEFAULT_FROM_EMAIL', 'noreply@coparentmanager.com')

        if not api_key or not api_secret:
            logger.error("❌ Credenziali Mailjet mancanti (MAILJET_API_KEY, MAILJET_SECRET_KEY)")
            if not fail_silently:
                raise Exception("Credenziali Mailjet mancanti")
            return False

        # Mailjet API v3.1 endpoint
        url = "https://api.mailjet.com/v3.1/send"

        # Prepara destinatari (supporta lista multipla)
        to_list = []
        for email in recipient_list:
            to_list.append({
                "Email": email,
                "Name": email  # Puoi personalizzare se hai i nomi
            })

        # Prepara payload
        payload = {
            "Messages": [{
                "From": {
                    "Email": from_email,
                    "Name": from_name
                },
                "To": to_list,
                "Subject": subject,
                "HTMLPart": html_content,
            }]
        }

        # Aggiungi text part se disponibile
        if text_content:
            payload["Messages"][0]["TextPart"] = text_content

        # Invia richiesta HTTP
        response = requests.post(
            url,
            auth=(api_key, api_secret),
            json=payload,
            timeout=10  # Timeout 10 secondi (non infinito come SMTP)
        )

        if response.status_code == 200:
            logger.info(f"✅ {log_prefix} inviata a {recipient_list}")
            return True
        else:
            error_msg = f"❌ Errore Mailjet API: {response.status_code} - {response.text}"
            logger.error(error_msg)
            if not fail_silently:
                raise Exception(error_msg)
            return False

    except requests.exceptions.Timeout:
        error_msg = f"❌ Timeout connessione Mailjet API per {log_prefix}"
        logger.error(error_msg)
        if not fail_silently:
            raise Exception(error_msg)
        return False

    except Exception as e:
        error_msg = f"❌ Errore invio {log_prefix}: {e}"
        logger.error(error_msg, exc_info=True)

        if settings.DEBUG:
            import traceback
            traceback.print_exc()

        if not fail_silently:
            raise

        return False