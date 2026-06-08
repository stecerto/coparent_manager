from django.conf import settings
from django.db import models

from core.fields import EncryptedTextField
from core.storage import EncryptedFileSystemStorage
from families.models import Family
from calendar_app.models import CalendarEvent

encrypted_chat_storage = EncryptedFileSystemStorage(location="media/encrypted_chat")
class FamilyMessage(models.Model):
    """
        Modello unificato per chat famiglia E chat privata.
        La distinzione avviene tramite:
          - recipient IS NULL → messaggio famiglia
          - recipient IS NOT NULL → messaggio privato
        PrivateMessage è stato rimosso per evitare duplicazione di logica
        (versioning, soft-delete, crittografia, export, history).
        """
    # ✅ NUOVO: Tipo di conversazione per gestire gruppi specifici
    THREAD_TYPES = [
        ('family', '👨‍👩‍👧‍👦 Gruppo Famiglia (Tutti)'),
        ('legal_a', '⚖️ Legale A (Avv.A + Gen.A)'),
        ('legal_b', '⚖️ Legale B (Avv.B + Gen.B)'),
        ('mediation', '🤝 Mediazione (Mediatore + Gen.A + Gen.B)'),
        ('consulting', '💼 Consulenza (Consulente + Gen.A + Gen.B)'),
        # ✅ NUOVI: Chat private 1-to-1
        ('mediation_private', '🔒 Mediazione Privata (Mediatore + Genitore)'),
        ('consultant_private', '🔒 Consulenza Privata (Consulente + Genitore)'),
        ('lawyer_private', '🔒 Avvocato Privato (Avvocato + Genitore)'),
        ('mediator_private', '🔒 Mediatore Privato (Mediatore + Genitore)'),

    ]

    family = models.ForeignKey("families.Family", on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    thread_type = models.CharField(
        max_length=20,
        choices=THREAD_TYPES,
        default='family',
        db_index=True
    )
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="received_messages")
    # NUOVO → risposta
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies"
    )

    content = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # -----------------------------
    # VERSIONING
    # -----------------------------
    is_active = models.BooleanField(default=True)
    previous_version = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="new_versions")
    version = models.PositiveIntegerField(default=1)
    # VERSIONING

    edited_at = models.DateTimeField(null=True, blank=True)

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_messages"
    )

    deleted_at = models.DateTimeField(null=True, blank=True)

    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_family_messages"
    )

    # LINK EVENTO
    linked_event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_messages"
    )

    linked_expense = models.ForeignKey(
        "expenses.Expense",  # Assicurati che il nome sia corretto
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_messages"
    )




    def __str__(self):
        return f"{self.sender.username} ({self.created_at}): {self.content[:30]}"



class MessageAttachment(models.Model):
    message = models.ForeignKey(
        "FamilyMessage",
        on_delete=models.CASCADE,
        related_name="attachments"
    )
    file = models.FileField(upload_to="message_attachments/", storage=encrypted_chat_storage)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name

