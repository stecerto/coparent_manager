from datetime import datetime

from django.utils import timezone

from calendar_app.services.calendar_service import create_event
from chat.models import FamilyMessage, MessageAttachment
from documents.models import Document, DocumentAuditLog


def send_message(
    family,
    sender,
    content,
    recipient=None,
    files=None,
    create_calendar_event=False,
    event_data=None,
    reply_to=None
):
    """
    Invia un messaggio con eventuali allegati.
    """

    message = FamilyMessage.objects.create(
        family=family,
        sender=sender,
        recipient=recipient,
        content=content,
        reply_to=reply_to
    )

    # Allegati
    if files:
        for f in files:
            attachment = MessageAttachment.objects.create(
                message=message,
                file=f,
                uploaded_by=sender
            )

            filename = f.name.lower()
            category = "chat"

            if "verbale" in filename:
                category = "minutes"
            elif "accordo" in filename:
                category = "agreement"

            shared_doc = Document.objects.create(
                family=family,
                owner=sender,
                uploaded_by=sender,
                title=f.name.rsplit(".", 1)[0],
                file=attachment.file,
                category=category,
                scope="shared",
                is_active=True
            )

            DocumentAuditLog.objects.create(
                document=shared_doc,
                user=sender,
                action="upload"
            )

    # Evento calendario
    event_data = event_data or {}

    if create_calendar_event and event_data:
        start_time_str = str(event_data.get("start_time"))
        end_time_str = str(event_data.get("end_time"))

        if start_time_str and end_time_str:
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)

            # se hai timezone aware (consigliato in Django)
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)

            if timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)

            event = create_event(
                family=family,
                title=event_data.get("title", content[:50]),
                start_time=start_time,
                end_time=end_time,
                created_by=sender,
                description=event_data.get("description", content)
            )

            message.linked_event = event
            message.save()
    return message

def update_message(message, user, new_content, files=None, create_calendar_event=False, event_data=None):
    """
    Versioning: disattiva il messaggio precedente e crea nuova versione.
    Allegati nuovi vengono aggiunti alla nuova versione.
    Allegati vecchi rimangono collegati alla versione precedente.
    """
    message.is_active = False
    message.edited_at = timezone.now()
    message.edited_by = user
    message.save()

    new_msg = FamilyMessage.objects.create(
        family=message.family,
        sender=message.sender,
        recipient=message.recipient,
        content=new_content,
        previous_version=message,
        version=message.version + 1
    )
    if files:
        for f in files:
            MessageAttachment.objects.create(
            message=new_msg,
            file=f,
            uploaded_by=user
        )

    if create_calendar_event and event_data:
        event = create_event(
            family=message.family,
            title=event_data.get("title", new_content[:50]),
            start_time=event_data.get("start_time"),
            end_time=event_data.get("end_time"),
            created_by=user,
            description=event_data.get("description", new_content)
        )
        new_msg.linked_event = event
        new_msg.save()

    return new_msg

def delete_message(message, user):
    """
    Soft delete con storico.
    """
    message.is_active = False
    message.deleted_at = timezone.now()
    message.deleted_by = user
    message.save()

    return message

def get_family_messages(family):
    """Recupera solo messaggi attivi di una famiglia"""
    return FamilyMessage.objects.filter(family=family, is_active=True).order_by("created_at")


def get_private_messages(family, user1, user2):
    """Recupera messaggi privati tra due utenti, solo attivi"""
    return FamilyMessage.objects.filter(
        family=family,
        sender__in=[user1, user2],
        recipient__in=[user1, user2],
        is_active=True
    ).order_by("created_at")

def get_all_versions(message):
    versions = []
    current = message

    while current:
        versions.append(current)
        current = current.previous_version

    return versions[::-1]
