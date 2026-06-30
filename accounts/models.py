

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta
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
    birth_date = models.DateField(null=True, blank=True)
    birth_place = models.CharField(max_length=255, blank=True)
    birth_place_code = models.CharField(max_length=10, blank=True)
    gender = models.CharField(max_length=1, choices=[("M", "M"), ("F", "F")])
    codice_fiscale = models.CharField(max_length=16, blank=True, null=True)
    phone = PhoneNumberField(null=True, blank=True)

    firm_name = models.CharField(max_length=100, blank=True)
    partita_iva = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Partita IVA",
        help_text="Obbligatoria per avvocati e professionisti"
    )

    cf_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Da calcolare"),
            ("calculated", "Calcolato"),
            ("manual", "Manuale"),
            ("invalid", "Non valido"),
        ],
        default="pending"
    )

    # ✅ PIANO ABBONAMENTO
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

    pending_plan = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Piano futuro (si attiva alla scadenza)"
    )
    pending_plan_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Quando partirà il piano pending"
    )

    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("active", "✅ Attivo"),
            ("pending_payment", "⏳ In attesa pagamento"),
            ("suspended", "🚫 Sospeso"),
            ("cancelled", "❌ Annullato"),
        ],
        default="active",
        help_text="Stato attuale dell'abbonamento"
    )

    auto_renew = models.BooleanField(
        default=True,
        help_text="Rinnovo automatico mensile"
    )

    last_payment_date = models.DateTimeField(null=True, blank=True)
    next_payment_date = models.DateTimeField(null=True, blank=True)

    # Stato
    setup_complete = models.BooleanField(default=False)

    # Privacy
    privacy_accepted_at = models.DateTimeField("Data accettazione privacy", null=True, blank=True)
    privacy_version_accepted = models.CharField("Versione policy accettata", max_length=10, default="1.0")

    def __str__(self):
        return f"Profilo di {self.user.email}"

    # ==========================================================
    # ✅ PROPRIETÀ E METODI (DEVONO ESSERE INDENTATI DENTRO LA CLASSE!)
    # ==========================================================

    @property
    def days_until_expiration(self):
        """Giorni rimanenti prima della scadenza"""
        if not self.plan_expires_at:
            return None
        if timezone.now() > self.plan_expires_at:
            return 0
        delta = self.plan_expires_at - timezone.now()
        return delta.days

    @property
    def is_expired(self):
        """Controlla se l'abbonamento è scaduto"""
        if not self.plan_expires_at:
            return False
        return timezone.now() > self.plan_expires_at

    @property
    def is_suspended(self):
        """Controlla se l'account è sospeso"""
        return self.payment_status == "suspended"

    # ✅ NUOVA PROPERTY AGGIUNTA QUI:
    @property
    def is_blocked(self):
        """Restituisce True se l'account è scaduto o sospeso (bloccato)"""
        return self.is_expired or self.is_suspended

    def activate_pending_plan(self):
        """Attiva il piano pending (chiamato alla scadenza o dopo il pagamento)"""
        if self.pending_plan:
            self.plan = self.pending_plan
            self.pending_plan = None
            self.pending_plan_start = None
            self.plan_started_at = timezone.now()
            self.plan_expires_at = timezone.now() + timedelta(days=30)
            self.payment_status = "active"  # Riattiva lo stato
            self.save()

    @property
    def role_base(self):
        """Restituisce il ruolo normalizzato senza suffissi _a/_b"""
        return RoleChoices.normalize_role(self.role)

    @property
    def is_professional(self):
        """True se l'utente è un professionista (avvocato, mediatore, consulente)"""
        return RoleChoices.is_professional(self.role)

    @property
    def is_parent(self):
        """True se l'utente è un genitore"""
        return RoleChoices.is_parent(self.role)

    @property
    def is_lawyer(self):
        return RoleChoices.is_lawyer(self.role)

    @property
    def is_mediator(self):
        return RoleChoices.is_mediator(self.role)

    @property
    def is_consultant(self):
        return RoleChoices.is_consultant(self.role)
'''
    def clean(self):
        """🔒 Blocca modifica del telefono dopo la creazione"""
        if self.pk:
            old = self.__class__.objects.get(pk=self.pk)
            if self.phone != old.phone:
                raise ValidationError("Il numero di telefono non può essere modificato dopo la registrazione.")
        super().clean()

'''