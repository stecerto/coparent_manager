import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import F
from django.utils import timezone

from core.choices import RoleChoices, AssignmentTypeChoices
from core.fields import EncryptedCharField


class Family(models.Model):
    CREATOR_ROLE_CHOICES = [
        ("parent_a", "Genitore A"),
        ("lawyer_a", "Avvocato A"),
    ]

    name = EncryptedCharField(max_length=255)
    # 🔑 Identificativo univoco (per inviti, link, API)
    code = models.UUIDField("Codice famiglia", default=uuid.uuid4, unique=False, editable=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_families"
    )

    creator_role = models.CharField(
        max_length=20,
        choices=CREATOR_ROLE_CHOICES,
        default="parent_a"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True)

    @property
    def surname(self):
        """
        Restituisce il cognome della famiglia.
        Priorità: cognome del creatore → ultima parola di `name` → stringa vuota.
        """
        if self.created_by and self.created_by.last_name:
            return self.created_by.last_name
        # Fallback: estrae l'ultima parola da "Famiglia Rossi" → "Rossi"
        return self.name.split()[-1] if self.name else ""

    def __str__(self):
        return self.name


class FamilyMember(models.Model):
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
    )

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="members"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="family_memberships"
    )

    is_primary = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['family', 'user']
        constraints = [
            models.UniqueConstraint(
                fields=["family", "user"],
                name="unique_family_user"
            ),
            models.UniqueConstraint(
                fields=["family", "role"],
                name="unique_family_role"
            )
        ]

    def clean(self):
        if FamilyMember.objects.filter(
                family=self.family,
                role=self.role
        ).exclude(pk=self.pk).exists():
            raise ValidationError(
                f"Ruolo {self.role} già assegnato"
            )

    def __str__(self):
        family_surname = self.family.surname if self.family else "N/D"
        return f"{family_surname} - {self.family.name if self.family else 'N/D'} - {self.user.email} - {self.role}"


class ChildSupportAgreement(models.Model):
    family = models.ForeignKey("Family", on_delete=models.CASCADE, related_name="support_agreements")

    # 📜 Dati Sentenza
    decree_number = models.CharField("Numero sentenza/accordo", max_length=100, blank=True)
    decree_date = models.DateField("Data sentenza", null=True, blank=True)
    decree_file = models.FileField("File sentenza", upload_to="legal/decrees/", null=True, blank=True)

    # Termini Pagamento
    monthly_amount = models.DecimalField("Importo mensile totale", max_digits=10, decimal_places=2)
    split_pct_parent_a = models.DecimalField(
        "% a carico Genitore A", max_digits=5, decimal_places=2,
        default=50.00, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    payment_day = models.PositiveIntegerField(
        "Giorno del mese", validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Es: 5 per il 5 di ogni mese"
    )
    start_date = models.DateField("Decorrenza")
    end_date = models.DateField("Scadenza (opzionale)", null=True, blank=True,
                                help_text="Di default fino al compimento della maggiore età")

    # 👶 Figli coinvolti
    children = models.ManyToManyField("children.ChildProfile", related_name="support_agreements")

    # 🔄 Versioning & Stato
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    previous_version = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name="new_versions")
    created_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        # ✅ Aggiorna automaticamente il default sul profilo figlio
        super().save(*args, **kwargs)
        # ✅ Aggiorna SOLO i figli che NON hanno un override esplicito
        self.children.filter(override_split_pct__isnull=True).update(
            contribution_pct_parent_a=self.split_pct_parent_a
        )

        # 📅 Genera eventi calendario
        from .services.agreement_service import generate_support_calendar_events
        generate_support_calendar_events(self)

    def __str__(self):
        return f"Mantenimento {self.decree_number or 'senza num.'} - €{self.monthly_amount}"


# ==============================================================================
# ✅ NUOVO MODELLO AGGIUNTO QUI: ConsultantAssignment
# ==============================================================================
class ConsultantAssignment(models.Model):
    """
    Traccia formalmente l'incarico di un consulente (CTU, consulente di parte, ecc.)
    all'interno di una famiglia, distinguendo la natura del mandato.
    """
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="consultant_assignments"
    )

    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consultant_assignments",
        limit_choices_to={'profile__role': RoleChoices.CONSULTANT},  # Garantisce integrità dei dati
        verbose_name="Consulente incaricato"
    )

    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentTypeChoices.choices,
        default=AssignmentTypeChoices.INDIVIDUAL,
        verbose_name="Tipo di incarico"
    )

    start_date = models.DateField("Data inizio incarico")
    end_date = models.DateField("Data fine incarico", null=True, blank=True)

    is_active = models.BooleanField(default=True, verbose_name="Incarico attivo")

    notes = models.TextField(
        "Note sull'incarico",
        blank=True,
        help_text="Es: Numero di ruolo CTU, oggetto specifico della consulenza, ecc."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Incarico Consulente"
        verbose_name_plural = "Incarichi Consulenti"
        constraints = [
            # Evita incarichi sovrapposti per lo stesso tipo nella stessa famiglia
            models.UniqueConstraint(
                fields=['family', 'assignment_type'],
                condition=models.Q(is_active=True),
                name='unique_active_assignment_per_family_and_type'
            )
        ]

    def __str__(self):
        return f"{self.consultant.email} - {self.get_assignment_type_display()} ({self.family.name})"


# =========================
# 🔹 INVITATIONS
# =========================
class Invitation(models.Model):
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
    )

    STATUS_CHOICES = [
        ("pending", "In attesa"),
        ("accepted", "Accettato"),
        ("expired", "Scaduto"),
        ("cancelled", "Annullato"),
        ("revoked", "Revocato"),
    ]

    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
    ]

    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default="email"
    )

    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="invitations",
        null=True,
        blank=True
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations"
    )

    display_name = models.CharField(max_length=255, blank=True, null=True)

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_invitations"
    )

    message = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    expire_at = models.DateTimeField(
        blank=True,
        null=True
    )

    accepted_at = models.DateTimeField(
        blank=True,
        null=True
    )

    last_sent_at = models.DateTimeField(
        blank=True,
        null=True
    )

    resend_count = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["token"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "email"],
                condition=models.Q(status="pending") & models.Q(email__isnull=False),
                name="unique_pending_invitation"
            )
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.expire_at:
            self.expire_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.expire_at is not None and timezone.now() > self.expire_at

    @property
    def is_pending(self):
        return self.status == "pending"

    def mark_accepted(self, user):
        self.status = "accepted"
        self.accepted_at = timezone.now()
        self.invited_user = user
        self.save()

    def mark_expired(self):
        if self.status == "pending":
            self.status = "expired"
            self.save(update_fields=["status"])

    def increment_resend(self):
        self.resend_count = F("resend_count") + 1
        self.last_sent_at = timezone.now()
        self.save(update_fields=["resend_count", "last_sent_at"])

    def __str__(self):
        return f"{self.email} - {self.role} ({self.status})"


class PaymentSubscription(models.Model):
    """Gestisce lo stato dei pagamenti per utenti a pagamento."""

    STATUS_CHOICES = [
        ('active', 'Attivo'),
        ('grace_period', 'Periodo di grazia (5 giorni)'),
        ('suspended', 'Sospeso'),
        ('cancelled', 'Cancellato'),
    ]

    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='subscription'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    current_plan = models.CharField(max_length=20, default='starter')

    pending_plan = models.CharField(max_length=20, blank=True, null=True)
    pending_plan_start = models.DateTimeField(null=True, blank=True)

    subscription_start = models.DateTimeField(default=timezone.now)
    subscription_end = models.DateTimeField()
    grace_period_end = models.DateTimeField(null=True, blank=True)

    last_payment_date = models.DateTimeField(null=True, blank=True)
    next_payment_date = models.DateTimeField(null=True, blank=True)

    payment_method = models.CharField(max_length=50, blank=True)
    payment_provider_id = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['subscription_end']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.current_plan} ({self.get_status_display()})"

    @property
    def is_expired(self):
        return timezone.now() > self.subscription_end

    @property
    def is_in_grace_period(self):
        if not self.grace_period_end:
            return False
        return self.subscription_end < timezone.now() <= self.grace_period_end

    def mark_as_suspended(self):
        self.status = 'suspended'
        self.save()
        self.user.is_active = False
        self.user.save()

    def extend_subscription(self, months=1):
        from dateutil.relativedelta import relativedelta
        new_end = self.subscription_end + relativedelta(months=months)
        self.subscription_end = new_end
        self.grace_period_end = new_end + timedelta(days=5)
        self.status = 'active'
        self.last_payment_date = timezone.now()
        self.next_payment_date = new_end
        self.save()

        if not self.user.is_active:
            self.user.is_active = True
            self.user.save()

    def activate_pending_plan(self):
        """Attiva il piano pending (chiamato alla scadenza o al pagamento)"""
        if self.pending_plan:
            self.current_plan = self.pending_plan
            self.pending_plan = None
            self.pending_plan_start = None

            if hasattr(self.user, 'profile'):
                self.user.profile.plan = self.current_plan
                self.user.profile.save()

            self.save()
            return True
        return False

    def save(self, *args, **kwargs):
        if not self.grace_period_end and self.subscription_end:
            self.grace_period_end = self.subscription_end + timedelta(days=5)

        if hasattr(self.user, 'profile') and self.current_plan:
            self.user.profile.plan = self.current_plan
            self.user.profile.save()

        super().save(*args, **kwargs)