from django.conf import settings
from django.db import models

from core.fields import EncryptedTextField
from core.storage import EncryptedFileSystemStorage
from families.models import Family
from calendar_app.models import CalendarEvent

# Storage crittografato per gli allegati delle chat
encrypted_chat_storage = EncryptedFileSystemStorage(location="media/encrypted_chat")


class FamilyMessage(models.Model):
    """
    Modello unificato per chat famiglia E chat privata.
    La distinzione avviene tramite:
      - recipient IS NULL → messaggio famiglia
      - recipient IS NOT NULL → messaggio privato
    """
    THREAD_TYPES = [
        ('family', '👨‍👩‍👧‍👦 Gruppo Famiglia (Tutti)'),
        ('legal_a', '⚖️ Legale A (Avv.A + Gen.A)'),
        ('legal_b', '⚖️ Legale B (Avv.B + Gen.B)'),
        ('mediation', '🤝 Mediazione (Mediatore + Gen.A + Gen.B)'),
        ('consulting', '💼 Consulenza (Consulente + Gen.A + Gen.B)'),
        # Chat private 1-to-1
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
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_messages"
    )
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies"
    )

    content = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # VERSIONING
    is_active = models.BooleanField(default=True)
    previous_version = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name="new_versions")
    version = models.PositiveIntegerField(default=1)
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

    # ✅ FASE C: Collegamento opzionale a Conversation per permessi granulari
    conversation = models.ForeignKey(
        'Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages',
        help_text="Se impostato, i permessi di visibilità seguono le regole della Conversation."
    )

    def __str__(self):
        return f"{self.sender.email} ({self.created_at.strftime('%d/%m %H:%M')}): {self.content[:30]}..."


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


class Conversation(models.Model):
    """
    Modello per gestire chat strutturate con permessi granulari.
    Utile per Mediazioni, Consulenze CTU o chat legali dedicate.
    """
    TYPE_CHOICES = [
        ("family", "Famiglia (Tutti)"),
        ("private", "Privata (1-a-1)"),
        ("mediation", "Mediazione (Genitori + Mediatore)"),
        ("legal", "Legale (Genitore + Avvocato)"),
        ("consultation", "Consulenza (Definita dal mandato)"),
    ]

    family = models.ForeignKey('families.Family', on_delete=models.CASCADE, related_name='conversations')
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255, blank=True, help_text="Es: 'Mediazione Rossi-Bianchi'")

    # Chi può vedere questa chat?
    # Può contenere ID utente (es. [12, 15]) o ruoli normalizzati (es. ['mediator', 'parent_a'])
    visible_to_roles = models.JSONField(
        default=list,
        help_text="Lista di ruoli (es. 'mediator') o ID utente autorizzati"
    )

    # Per chat 1-a-1 o consulenze individuali (Usa settings.AUTH_USER_MODEL per evitare import circolari)
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='conversations',
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.get_type_display()} - {self.family.name}"

    def can_user_access(self, user):
        """
        Verifica se un utente ha i permessi per vedere/partecipare a questa conversazione.
        """
        if not user or not user.is_authenticated:
            return False

        # 1. Se l'utente è esplicitamente nella lista dei partecipanti, ha accesso
        if self.participants.filter(id=user.id).exists():
            return True

        # 2. Controllo basato sui ruoli
        if self.visible_to_roles:
            from core.choices import RoleChoices
            from families.utils import get_user_role_in_family

            # Ottieni il ruolo dell'utente in questa specifica famiglia
            user_role = get_user_role_in_family(user, self.family)
            normalized_role = RoleChoices.normalize_role(user_role)

            # Se il ruolo normalizzato è nella lista, o se l'ID utente è nella lista
            if normalized_role in self.visible_to_roles or str(user.id) in self.visible_to_roles:
                return True

        # Fallback: se la lista è vuota e non è nei participants, nega l'accesso (sicurezza first)
        return False