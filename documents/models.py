from django.db import models
from django.conf import settings
from families.models import Family


def family_document_path(instance, filename):
    family_name = instance.family.name.lower().replace(" ", "_")   #membership.user.first_name

    if instance.scope == "shared":
        folder = "shared_documents"
    else:
        owner_name = instance.owner.username.lower()
        folder = f"private/{owner_name}"

    return f"families/{family_name}/{folder}/{filename}"


class Document(models.Model):
    CATEGORY_CHOICES = [
        ("payslip", "Busta paga"),
        ("tax_return", "Dichiarazione redditi"),
        ("chat", "Documento chat"),
        ("agreement", "Accordo"),
        ("minutes", "Verbale"),
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
        related_name="owned_documents"
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_documents"
    )

    title = models.CharField(max_length=255)

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

    file = models.FileField(upload_to=family_document_path)

    reference_year = models.IntegerField(
        null=True,
        blank=True
    )

    version = models.IntegerField(default=1)

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

    def __str__(self):
        return f"{self.title} - v{self.version}"


class DocumentVersion(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="versions"
    )

    file = models.FileField(upload_to=family_document_path)

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
        ("upload", "Upload"),
        ("view", "Visualizzazione"),
        ("download", "Download"),
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
    ROLE_CHOICES = [
        ("parent_a", "Genitore A"),
        ("parent_b", "Genitore B"),
        ("lawyer_a", "Avvocato A"),
        ("lawyer_b", "Avvocato B"),
    ]

    document = models.ForeignKey(
        "Document",
        on_delete=models.CASCADE,
        related_name="signatures"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("document", "user")

    def __str__(self):
        return f"{self.user} - {self.role}"

class DocumentApproval(models.Model):
    ROLE_CHOICES = [
        ("parent_a", "Genitore A"),
        ("parent_b", "Genitore B"),
        ("lawyer_a", "Avvocato A"),
        ("lawyer_b", "Avvocato B"),
    ]

    document = models.ForeignKey(
        "Document",
        on_delete=models.CASCADE,
        related_name="approvals"
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("upload", "Upload"),
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