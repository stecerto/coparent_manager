import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)


from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def send_html_email(
    subject,
    recipient_list,
    template_name,
    context,
    from_email=None,
    fail_silently=False,
    log_prefix="Email"
):
    try:
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )

        msg.attach_alternative(html_content, "text/html")

        # ✅ IMPORTANTISSIMO
        msg.mixed_subtype = "related"

        msg.send(fail_silently=fail_silently)

        logger.info(f"✅ {log_prefix} inviata a {recipient_list}")

        return True

    except Exception as e:
        logger.error(f"❌ Errore invio {log_prefix}: {e}")

        if settings.DEBUG:
            import traceback
            traceback.print_exc()

        return False