from django.conf import settings
from django.db import models

from core.encryption import encrypt_text, decrypt_text
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


class ProfessionalThread(models.Model):
    """
    Thread di chat tra professionisti dello studio.
    Supporta chat generali (tutti i professionisti) e chat private (1-a-1 o gruppi).
    """

    # ✅ TIPI DI THREAD
    # - studio_general: chat visibile a tutti i professionisti
    # - private: chat privata tra 2 o più professionisti specifici
    THREAD_TYPES = [
        ('studio_general', 'Chat Generale Studio'),
        ('private', 'Chat Privata'),  # ✅ NUOVO
    ]

    # ✅ CAMPI BASE
    name = models.CharField(
        max_length=200,
        help_text="Nome del thread (per chat private: nomi dei partecipanti)"
    )
    thread_type = models.CharField(
        max_length=50,
        choices=THREAD_TYPES,
        default='studio_general',
        help_text="Tipo di thread determina chi può vedere e partecipare"
    )

    # ✅ PARTECIPANTI (ManyToMany)
    # Per chat generali: vuoto (tutti i professionisti possono partecipare)
    # Per chat private: lista specifica dei partecipanti
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='professional_threads',
        blank=True,
        help_text="Partecipanti specifici (solo per chat private). Vuoto = chat generale"
    )

    # ✅ METADATA
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_professional_threads',
        help_text="Chi ha creato il thread (per chat private)"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Thread Professionisti"
        verbose_name_plural = "Thread Professionisti"
        ordering = ['-created_at']

    def __str__(self):
        """
        Rappresentazione leggibile del thread.
        Per chat private: mostra i nomi dei partecipanti.
        Per chat generali: mostra il nome del thread.
        """
        if self.thread_type == 'private':
            # Recupera i nomi dei partecipanti
            participant_names = []
            for p in self.participants.all():
                # Usa get_full_name() se disponibile, altrimenti email
                name = p.get_full_name() if p.get_full_name() else p.email
                participant_names.append(name)

            # Unisci i nomi con " e "
            return f"Chat privata: {' e '.join(participant_names)}"
        else:
            # Chat generale: mostra il nome del thread
            return self.name

    def get_other_participants(self, user):
        """
        Restituisce tutti i partecipanti tranne l'utente corrente.
        Utile per mostrare "con chi stai chattando".
        """
        return self.participants.exclude(id=user.id)

    def get_display_name(self, user):
        """
        Restituisce il nome visualizzato del thread per un utente specifico.
        Per chat private: nomi degli altri partecipanti.
        Per chat generali: nome del thread.
        """
        if self.thread_type == 'private':
            others = self.get_other_participants(user)
            names = []
            for p in others:
                name = p.get_full_name() if p.get_full_name() else p.email
                names.append(name)
            return ', '.join(names) if names else 'Chat privata'
        else:
            return self.name


from core.fields import EncryptedTextField  # ✅ Usa il tuo campo custom


class ProfessionalMessage(models.Model):
    """
    Messaggio tra professionisti dello studio.
    Il contenuto è criptato automaticamente nel database.
    """
    thread = models.ForeignKey(
        ProfessionalThread,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='professional_messages_sent'
    )

    # ✅ Campo criptato automaticamente (usa il tuo EncryptedTextField)
    # Nel DB viene salvato come testo criptato (illeggibile)
    # Quando lo leggi, viene decriptato automaticamente
    content = EncryptedTextField(
        blank=True,
        help_text="Contenuto del messaggio (criptato nel DB)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        # ✅ Configurazione del modello (SOLO attributi, non metodi!)
        ordering = ['created_at']
        verbose_name = "Messaggio Professionisti"
        verbose_name_plural = "Messaggi Professionisti"

    def __str__(self):
        """Rappresentazione leggibile del messaggio"""
        return f"{self.sender} - {self.created_at}"


import os
from django.conf import settings
from core.encryption import encrypt_bytes, decrypt_bytes


class ProfessionalAttachment(models.Model):
    """
    Allegato a un messaggio tra professionisti.
    Il file viene criptato prima di essere salvato su disco.
    """
    message = models.ForeignKey(
        ProfessionalMessage,
        on_delete=models.CASCADE,
        related_name='attachments'
    )

    # ✅ File criptato (salvato su disco con estensione .enc)
    # Il FileField originale viene sostituito da questo campo
    encrypted_file = models.FileField(
        upload_to='professional_chat/encrypted/%Y/%m/',
        help_text="File criptato (salvato su disco)"
    )

    # ✅ Metadati del file (NON criptati, servono per la UI)
    original_filename = models.CharField(
        max_length=255,
        help_text="Nome originale del file (per display)"
    )
    file_size = models.PositiveIntegerField(
        default=0,
        help_text="Dimensione del file in bytes"
    )
    content_type = models.CharField(
        max_length=100,
        default='application/octet-stream',
        help_text="MIME type del file originale"
    )

    # ✅ Chi ha caricato il file
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Allegato Professionisti"
        verbose_name_plural = "Allegati Professionisti"

    def __str__(self):
        """Rappresentazione leggibile dell'allegato"""
        return self.original_filename

    # ============================================
    # 📤 UPLOAD: Cripta il file prima di salvarlo
    # ============================================
    def save(self, *args, **kwargs):
        """
        Override del metodo save().
        Se c'è un nuovo file da caricare, lo cripta prima di salvarlo.
        """
        # Controlla se c'è un nuovo file da processare
        if self.encrypted_file and hasattr(self.encrypted_file, 'file'):
            # Leggi il contenuto del file originale
            original_content = self.encrypted_file.read()

            # ✅ Cripta il contenuto
            encrypted_content = encrypt_bytes(original_content)

            # ✅ Cambia l'estensione a .enc per indicare che è criptato
            original_name = self.encrypted_file.name
            if not original_name.endswith('.enc'):
                base_name = os.path.splitext(original_name)[0]
                self.encrypted_file.name = f"{base_name}.enc"

            # Salva i metadati del file originale
            if not self.original_filename:
                self.original_filename = os.path.basename(original_name)
            if not self.file_size:
                self.file_size = len(original_content)

            # ✅ Salva il file criptato
            # Creiamo un nuovo file in memoria con il contenuto criptato
            from django.core.files.base import ContentFile
            self.encrypted_file = ContentFile(
                encrypted_content,
                name=self.encrypted_file.name
            )

        # Chiama il save originale
        super().save(*args, **kwargs)

    # ============================================
    # 📥 DOWNLOAD: Decripta il file prima di servirlo
    # ============================================
    def get_decrypted_file(self):
        """
        Restituisce il contenuto decriptato del file.
        Utile per servire il file all'utente in download.

        Returns:
            bytes: Contenuto decriptato del file
        """
        try:
            # Leggi il file criptato dal disco
            with self.encrypted_file.open('rb') as f:
                encrypted_content = f.read()

            # ✅ Decripta il contenuto
            return decrypt_bytes(encrypted_content)
        except Exception as e:
            # Log dell'errore (opzionale)
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Errore decriptazione allegato {self.id}: {e}")
            return None

    def get_download_filename(self):
        """
        Restituisce il nome del file per il download.
        Rimuove l'estensione .enc se presente.
        """
        filename = self.original_filename or self.encrypted_file.name
        if filename.endswith('.enc'):
            filename = filename[:-4]
        return filename