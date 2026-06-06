from django.core.mail import send_mail


def notify_document_status(document, message):
    family = document.family

    users = family.members.select_related("user")

    emails = [m.user.email for m in users if m.user.email]

    send_mail(
        subject=f"[Family Legal] Documento: {document.title}",
        message=message,
        from_email=None,
        recipient_list=emails,
        fail_silently=True
    )