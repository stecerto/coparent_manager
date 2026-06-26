# chat/services/message_service.py
"""
Servizi per la gestione dei messaggi della chat.
NON contiene definizioni di modelli (sono in chat/models.py).
"""
from django.db.models import Q
from django.utils import timezone

from chat.models import FamilyMessage, Conversation


def get_family_messages(family, user, thread_type='family', limit=50):
    """
    Recupera i messaggi di una famiglia per un thread specifico.
    Gestisce permessi in base al thread_type.
    """
    qs = FamilyMessage.objects.filter(
        family=family,
        thread_type=thread_type,
        is_active=True,
        deleted_at__isnull=True
    ).select_related('sender', 'reply_to').order_by('-created_at')

    # Filtra per visibilità in base al thread
    if thread_type == 'family':
        pass  # Tutti i membri della famiglia vedono
    elif thread_type in ['legal_a', 'legal_b']:
        # Solo avvocato + genitore del lato corrispondente
        qs = qs.filter(
            Q(sender__family_memberships__family=family) &
            Q(sender__family_memberships__role__in=_get_allowed_roles(thread_type))
        )
    # Aggiungi altri filtri per mediation, consulting, private...

    return qs[:limit]


def get_unread_count(user, family=None):
    """Conta messaggi non letti per un utente"""
    from datetime import timedelta
    recent_cutoff = timezone.now() - timedelta(days=7)

    qs = FamilyMessage.objects.filter(
        recipient=user,
        created_at__gte=recent_cutoff,
        is_active=True,
        deleted_at__isnull=True
    )

    if family:
        qs = qs.filter(family=family)

    return qs.count()


from django.utils import timezone
from chat.models import FamilyMessage, MessageAttachment
from documents.models import Document
from calendar_app.services.calendar_service import create_event


def send_message(
        sender,
        family,
        content,
        thread_type='family',
        recipient=None,
        reply_to=None,
        files=None,  # ✅ AGGIUNTO: Lista di file allegati
        create_calendar_event=False,  # ✅ AGGIUNTO: Flag per creare evento
        event_data=None  # ✅ AGGIUNTO: Dati dell'evento da creare
):
    """
    Crea un nuovo messaggio con validazione permessi, allegati e opzionale creazione evento calendario.

    Args:
        sender: Utente che invia il messaggio
        family: Famiglia di destinazione
        content: Testo del messaggio
        thread_type: Tipo di thread (family, legal_a, legal_b, mediation_private, etc.)
        recipient: Utente destinatario (None per messaggi di gruppo)
        reply_to: Messaggio a cui si sta rispondendo (opzionale)
        files: Lista di file allegati (opzionale)
        create_calendar_event: Se True, crea un evento calendario (opzionale)
        event_data: Dizionario con dati dell'evento (opzionale)

    Returns:
        FamilyMessage: Il messaggio creato
    """

    # 1. Crea il messaggio
    message = FamilyMessage.objects.create(
        sender=sender,
        family=family,
        content=content,
        thread_type=thread_type,
        recipient=recipient,
        reply_to=reply_to,
    )

    # 2. Gestisci allegati
    if files:
        for file in files:
            MessageAttachment.objects.create(
                message=message,
                file=file,
                filename=file.name,
                file_size=file.size,
                content_type=file.content_type or 'application/octet-stream',
                uploaded_by=sender
            )

            # ✅ Se è un thread privato con professionista, salva anche come documento
            if thread_type in ['legal_a', 'legal_b', 'mediation_private', 'consultant_private']:
                Document.objects.create(
                    family=family,
                    uploaded_by=sender,
                    owner=sender,
                    file=file,
                    title=file.name[:100],
                    is_private=True,
                    scope="private"
                )

    # 3. Crea evento calendario se richiesto
    if create_calendar_event and event_data:
        try:
            # Estrai i dati dall'event_data
            title = event_data.get('title', content[:50])
            start_time = event_data.get('start_time', timezone.now())
            end_time = event_data.get('end_time', timezone.now())
            description = event_data.get('description', content)
            event_type = event_data.get('event_type', 'other')
            children_ids = event_data.get('children_ids', [])

            # Recupera i figli se specificati
            children = []
            if children_ids:
                children = family.children.filter(id__in=children_ids)

            # Crea l'evento
            event = create_event(
                family=family,
                title=title,
                start_time=start_time,
                end_time=end_time,
                created_by=sender,
                description=description,
                event_type=event_type,
                children=children
            )

            # ✅ Collega l'evento al messaggio (se hai un campo linked_event)
            # message.linked_event = event
            # message.save(update_fields=['linked_event'])

        except Exception as e:
            # Logga l'errore ma non bloccare la creazione del messaggio
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Errore creazione evento da chat: {e}", exc_info=True)

    return message


def delete_message(message, user):
    """Eliminazione soft (versioning) di un messaggio"""
    message.deleted_at = timezone.now()
    message.deleted_by = user
    message.is_active = False
    message.save(update_fields=['deleted_at', 'deleted_by', 'is_active'])


def edit_message(message, new_content, user):
    """Modifica un messaggio creando una nuova versione"""
    # Crea versione precedente
    old_version = FamilyMessage.objects.create(
        family=message.family,
        sender=message.sender,
        content=message.content,
        thread_type=message.thread_type,
        recipient=message.recipient,
        reply_to=message.reply_to,
        version=message.version,
        is_active=False,
    )

    # Aggiorna messaggio corrente
    message.content = new_content
    message.version += 1
    message.previous_version = old_version
    message.edited_at = timezone.now()
    message.edited_by = user
    message.save()

    return message


def _get_allowed_roles(thread_type):
    """Helper: restituisce i ruoli permessi per un thread"""
    role_map = {
        'legal_a': ['lawyer_a', 'parent_a'],
        'legal_b': ['lawyer_b', 'parent_b'],
        'mediation': ['mediator', 'parent_a', 'parent_b'],
        'consulting': ['consultant', 'parent_a', 'parent_b'],
    }
    return role_map.get(thread_type, [])