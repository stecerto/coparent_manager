import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from calendar_app.services.calendar_service import create_event
from chat.models import FamilyMessage, MessageAttachment
from documents.models import Document, DocumentAuditLog
from calendar_app.models import CalendarEvent

logger = logging.getLogger(__name__)


@transaction.atomic
def send_message(
        family,
        sender,
        content,
        recipient=None,
        files=None,
        create_calendar_event=False,
        event_data=None,
        reply_to=None,
        thread_type="family"
):
    """
    Invia un messaggio con eventuali allegati e crea evento calendario (se richiesto).
    ✅ FIX: Crea CalendarEvent direttamente con dati filtrati per evitare TypeError('amount').
    """
    files = files or []

    # 1. Crea messaggio
    message = FamilyMessage.objects.create(
        family=family,
        sender=sender,
        recipient=recipient,
        content=content,
        reply_to=reply_to,
        thread_type=thread_type
    )

    # 2. Gestione Allegati (Logica originale mantenuta intatta)
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

    # 3. Evento Calendario (MODIFICA CHIRURGICA)
    # ✅ FIX: Usiamo safe_data per creare l'evento direttamente, bypassando create_event service
    # che probabilmente passava **kwargs includendo 'amount'.
    # Evento calendario
    if create_calendar_event and event_data:
        try:
            start_time_str = str(event_data.get("start_time"))
            end_time_str = str(event_data.get("end_time"))

            if start_time_str and end_time_str:
                start_time = datetime.fromisoformat(start_time_str)
                end_time = datetime.fromisoformat(end_time_str)

                if timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)
                if timezone.is_naive(end_time):
                    end_time = timezone.make_aware(end_time)

                # ✅ Estrai e rimuovi children_ids prima di creare l'evento
                children_ids = event_data.pop("children_ids", [])

                safe_data = {
                    "family": family,
                    "created_by": sender,
                    "title": str(event_data.get("title", content[:50]))[:200],
                    "description": str(event_data.get("description", content)),
                    "start_time": start_time,
                    "end_time": end_time,
                    "event_type": event_data.get("event_type", "other"),
                    "source": event_data.get("source", "chat"),
                    "linked_id": event_data.get("linked_id"),
                }
                safe_data = {k: v for k, v in safe_data.items() if v is not None}

                # Creazione evento
                event = CalendarEvent.objects.create(**safe_data)

                # ✅ Collegamento figli (ManyToMany richiede .set() dopo il create)
                if children_ids:
                    from children.models import ChildProfile
                    # Sicurezza: prende solo figli appartenenti a questa famiglia
                    children = ChildProfile.objects.filter(id__in=children_ids, family=family, is_active=True)
                    event.children.set(children)

                message.linked_event = event
                message.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"❌ Errore creazione evento calendario: {e}", exc_info=True)


    logger.info(f"🔔 NOTIFICA - recipient: {recipient}, thread_type: {thread_type}")
    # 🔔 NOTIFICA (se messaggio privato 1-to-1)
    if recipient and thread_type in ['legal_a', 'legal_b', 'mediation_private', 'consultant_private', 'lawyer_private', 'mediator_private']:
        try:
            from notifications.services import create_notification
            create_notification(
                user=recipient,
                notification_type="chat_private",
                title=f"💬 Nuovo messaggio da {sender.first_name or sender.email}",
                message=content[:150] + ("..." if len(content) > 150 else ""),
                target_url=f"/chat/?family_id={family.id}&thread={thread_type}",
                target_model="FamilyMessage",
                target_id=message.id,
                metadata={
                    "sender_id": sender.id,
                    "family_id": family.id,
                    "thread_type": thread_type,
                },
                #send_email=True
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"❌ Errore notifica chat: {e}", exc_info=True)
            # Non bloccare il flusso se la notifica fallisce

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
