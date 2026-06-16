from django.db import models
from django.conf import settings
from django.utils import timezone

from core.choices import RoleChoices
from core.fields import EncryptedCharField
from core.storage import EncryptedFileSystemStorage
from families.models import Family


def family_document_path(instance, filename):
    family_name = instance.family.name.lower().replace(" ", "_")

    if instance.scope == "shared":
        folder = "shared_documents"
    else:
        owner_name = instance.owner.username.lower()
        folder = f"private/{owner_name}"

    return f"families/{family_name}/{folder}/{filename}"


# ✅ NUOVA FUNZIONE: Percorso specifico per gli accordi di mediazione
def mediation_agreement_path(instance, filename):
    """Percorso dedicato per i PDF degli accordi di mediazione, separato dai documenti generici."""
    family_name = instance.family.name.lower().replace(" ", "_")
    return f"families/{family_name}/mediation_agreements/{filename}"


# ✅ Storage criptato per i documenti
encrypted_storage = EncryptedFileSystemStorage(location="media/encrypted_docs")


class Document(models.Model):
    CATEGORY_CHOICES = [
        ("payslip", "Busta paga"),
        ("tax_return", "Dichiarazione redditi"),
        ("chat", "Documento chat"),
        ("agreement", "Accordo"),
        ("minutes", "Verbale"),
        ("payment_proof", "Prova di pagamento"),
        ("ruling", "📜 Sentenza"),
        ("generic", "Documento generico"),
    ]
    STATUS_CHOICES = [
        ("draft", "Bozza"),
        ("review", "In revisione"),
        ("approved", "Approvato"),
        ("signed", "Firmato"),
        ("locked", "Bloccato"),
        ("archived", "Archiviato"),
    ]
    SCOPE_CHOICES = [
        ("private", "Privato"),
        ("shared", "Condiviso"),
    ]

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="owned_documents"
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_documents"
    )

    title = EncryptedCharField(max_length=255)

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="generic"
    )

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default="private"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft"
    )

    file = models.FileField(upload_to=family_document_path, storage=encrypted_storage)

    reference_year = models.IntegerField(
        null=True,
        blank=True
    )

    versions = models.IntegerField(default=1)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_documents"
    )
    expense = models.ForeignKey(
        "expenses.Expense",
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True
    )
    is_private = models.BooleanField(
        default=False,
        verbose_name="Documento Riservato",
        help_text="Se attivo, il documento sarà visibile solo ai partecipanti della chat privata."
    )
    file_size = models.BigIntegerField(null=True, blank=True, editable=False)

    expiration_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data di scadenza",
        help_text="Data di scadenza del documento (opzionale). Se impostata, genererà un avviso."
    )

    # ✅ Dati strutturati estratti automaticamente dalle sentenze
    extracted_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Dati estratti",
        help_text="Dati strutturati estratti automaticamente dal PDF (mantenimento, affidamento, ecc.)"
    )

    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - v{self.versions}"


class DocumentVersion(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="version_history"
    )

    file = models.FileField(upload_to=family_document_path, storage=encrypted_storage)

    version = models.IntegerField()

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document.title} - v{self.version}"


class DocumentAuditLog(models.Model):
    ACTION_CHOICES = [
        ("upload", "Carica"),
        ("view", "Visualizzazione"),
        ("download", "Scarica"),
        ("update", "Aggiornamento"),
    ]

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} - {self.document.title}"


class DocumentSignature(models.Model):
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
    )

    document = models.ForeignKey(
        "Document",
        on_delete=models.CASCADE,
        related_name="signatures"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("document", "user")

    def __str__(self):
        return f"{self.user} - {self.role}"


class DocumentApproval(models.Model):
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices
    )

    document = models.ForeignKey(
        "Document",
        on_delete=models.CASCADE,
        related_name="approvals"
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("upload", "Carica"),
        ("edit", "Modifica"),
        ("approve", "Approvazione"),
        ("sign", "Firma"),
        ("delete", "Cancellazione"),
        ("event", "Evento"),
        ("message", "Messaggio"),
    ]

    family = models.ForeignKey("families.Family", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()

    document = models.ForeignKey(
        "Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    created_at = models.DateTimeField(auto_now_add=True)


# ==============================================================================
# ✅ NUOVI MODELLI AGGIUNTI: MediationAgreement e MediationAgreementSignature
# ==============================================================================

class MediationAgreement(models.Model):
    """
    Modello specifico per gestire gli accordi di mediazione.
    Traccia il mediatore, lo stato del processo e il PDF finale immutabile.
    """
    STATUS_CHOICES = [
        ("draft", "Bozza"),
        ("review", "In revisione dalle parti"),
        ("signing", "In fase di firma"),
        ("completed", "Completato e Firmato"),
        ("archived", "Archiviato"),
    ]

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="mediation_agreements"
    )

    mediator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mediated_agreements",
        limit_choices_to={'profile__role': RoleChoices.MEDIATOR},
        verbose_name="Mediatore incaricato"
    )

    title = EncryptedCharField(max_length=255, verbose_name="Titolo dell'accordo")
    description = models.TextField("Descrizione o oggetto della mediazione", blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft"
    )

    # Il PDF finale immutabile (una volta firmato, non deve essere sovrascritto)
    final_pdf = models.FileField(
        "PDF Accordo Firmato",
        upload_to=mediation_agreement_path,
        storage=encrypted_storage,
        null=True,
        blank=True
    )

    # Hash del file per garantire l'immutabilità (verifica che il PDF non sia stato alterato)
    pdf_hash = models.CharField(
        "Hash di integrità del PDF",
        max_length=64,  # SHA-256
        blank=True,
        editable=False,
        help_text="Generato automaticamente al caricamento del PDF finale."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Accordo di Mediazione"
        verbose_name_plural = "Accordi di Mediazione"

    def __str__(self):
        return f"Accordo: {self.title} ({self.family.name})"

    def save(self, *args, **kwargs):
        # Calcola l'hash del file se è stato appena caricato e non c'è già un hash
        if self.final_pdf and not self.pdf_hash:
            import hashlib
            try:
                # Legge il contenuto del file per generare l'hash SHA-256
                file_content = self.final_pdf.read()
                self.pdf_hash = hashlib.sha256(file_content).hexdigest()
                self.final_pdf.seek(0)  # Reset del puntatore del file per evitare problemi successivi
            except Exception:
                pass  # Fallback sicuro se il file non è ancora leggibile in questa fase del save

        if self.status == "completed" and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)


class MediationAgreementSignature(models.Model):
    """
    Traccia le firme specifiche su un accordo di mediazione.
    Include dati forensi (IP, timestamp) per validità legale e tracciabilità.
    """
    agreement = models.ForeignKey(
        MediationAgreement,
        on_delete=models.CASCADE,
        related_name="signatures"
    )

    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mediation_signatures"
    )

    role_at_signing = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        help_text="Ruolo dell'utente al momento della firma"
    )

    ip_address = models.GenericIPAddressField("Indirizzo IP al momento della firma", null=True, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)

    # Dati crittografati della firma (es. token del provider di firma digitale o metadati)
    signature_data = EncryptedCharField(
        "Dati firma crittografati",
        max_length=500,
        blank=True,
        help_text="Token o metadati del provider di firma digitale"
    )

    class Meta:
        unique_together = ("agreement", "signer")
        ordering = ['signed_at']
        verbose_name = "Firma Accordo di Mediazione"
        verbose_name_plural = "Firme Accordi di Mediazione"

    def __str__(self):
        return f"Firma di {self.signer.email} su {self.agreement.title}"