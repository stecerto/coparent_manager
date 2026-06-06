from django.db import models
from django.conf import settings

from core.choices import RoleChoices
from core.fields import EncryptedCharField
from core.storage import EncryptedFileSystemStorage
from families.models import Family


def family_document_path(instance, filename):
    family_name = instance.family.name.lower().replace(" ", "_")   #membership.user.first_name

    if instance.scope == "shared":
        folder = "shared_documents"
    else:
        owner_name = instance.owner.username.lower()
        folder = f"private/{owner_name}"

    return f"families/{family_name}/{folder}/{filename}"

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
    #current_version = models.IntegerField(default=1, db_column='version')  # mantiene il nome DB

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