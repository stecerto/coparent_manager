

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

from core.choices import RoleChoices


# =========================
# 🔹 USER
# =========================
class User(AbstractUser):
    username = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    @property
    def display_name(self):
        """Restituisce il primo nome disponibile"""
        return self.last_name or self.username or self.email

    @property
    def display_complet_name(self):
        # ✅ FIX: Usava self.created_by (inesistente). Ora usa i campi dell'utente.
        parts = [self.last_name, self.first_name]
        return " ".join(p for p in parts if p).strip() or self.email

    def clean(self):
        """🔒 Safety-net: impedisce modifiche a email, nome e cognome dopo la creazione"""
        if self.pk:  # Solo in update
            old = self.__class__.objects.get(pk=self.pk)
            for field in ['email', 'first_name', 'last_name']:
                if getattr(self, field) != getattr(old, field):
                    raise ValidationError(f"Il campo '{field}' è bloccato dopo la registrazione.")
        super().clean()


# =========================
# 🔹 USER PROFILE
# =========================
class UserProfile(models.Model):
    role = models.CharField(
        max_length=20,
        choices=[
            (RoleChoices.PARENT, 'Genitore'),
            (RoleChoices.LAWYER, 'Avvocato'),
            (RoleChoices.MEDIATOR, 'Mediatore'),
            (RoleChoices.CONSULTANT, 'Consulente'),
        ],
        default=RoleChoices.PARENT
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    # Dati personali
    address = models.CharField(max_length=255, blank=True)
    birth_date = models.DateField(default=timezone.now)

    birth_place = models.CharField(max_length=255, blank=True)
    phone = PhoneNumberField(null=True, blank=True)

    firm_name = models.CharField(max_length=100, blank=True)
    partita_iva = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Partita IVA",
        help_text="Obbligatoria per avvocati e professionisti"
    )


    # ✅ NUOVO: Piano scelto alla registrazione
    plan = models.CharField(
        max_length=20,
        choices=[
            ("starter", "Starter"),
            ("pro", "Pro"),
            ("enterprise", "Enterprise"),
        ],
        default="starter",
        help_text="Piano di abbonamento scelto"
    )
    plan_started_at = models.DateTimeField(null=True, blank=True)
    plan_expires_at = models.DateTimeField(null=True, blank=True)
    # Stato
    setup_complete = models.BooleanField(default=False)
    # privacy
    privacy_accepted_at = models.DateTimeField("Data accettazione privacy", null=True, blank=True)
    privacy_version_accepted = models.CharField("Versione policy accettata", max_length=10, default="1.0")

    def __str__(self):
        return f"Profilo di {self.user.email}"
'''
    def clean(self):
        """🔒 Blocca modifica del telefono dopo la creazione"""
        if self.pk:
            old = self.__class__.objects.get(pk=self.pk)
            if self.phone != old.phone:
                raise ValidationError("Il numero di telefono non può essere modificato dopo la registrazione.")
        super().clean()

'''