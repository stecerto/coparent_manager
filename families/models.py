import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F


class Family(models.Model):
    CREATOR_ROLE_CHOICES = [
        ("parent_a", "Parent A"),
        ("lawyer_a", "Lawyer A"),
    ]

    name = models.CharField(max_length=255)

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

    def __str__(self):
        return self.name



class FamilyMember(models.Model):
    ROLE_CHOICES = [
        ("parent_a", "Parent A"),
        ("parent_b", "Parent B"),
        ("lawyer_a", "Lawyer A"),
        ("lawyer_b", "Lawyer B"),
    ]

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

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    is_primary = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["family", "user"],
                name="unique_family_user"
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
        return f"{self.family.name} - {self.user.email} - {self.role}"


# =========================
# 🔹 INVITATIONS
# =========================
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta


class Invitation(models.Model):
    ROLE_CHOICES = [
        ("parent_a", "Genitore A"),
        ("parent_b", "Genitore B"),
        ("lawyer_a", "Avvocato A"),
        ("lawyer_b", "Avvocato B"),
        ("mediator", "Mediatore"),
        ("consultant", "Consulente"),
    ]

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
        related_name="invitations"
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations"
    )

    display_name = models.CharField(max_length=255, blank=True, null=True)

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES
    )

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

