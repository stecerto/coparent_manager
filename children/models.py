from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q


class ChildProfile(models.Model):
    AFFIDAMENTO_GENITORI = [
        ("shared_custody", "Affidamento condiviso"),
        ("sole_custody_a", "Affidamento esclusivo Genitore A"),
        ("sole_custody_b", "Affidamento esclusivo Genitore B"),
        ]

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="children"
    )

    name = models.CharField(max_length=255)
    surname = models.CharField(max_length=255)
    birth_date = models.DateField()

    notes = models.TextField(blank=True)
    # ✅ NUOVI CAMPI
    custody_type = models.CharField(
        max_length=20,
        choices=AFFIDAMENTO_GENITORI,
        default="shared_custody",
        verbose_name="Tipo di affidamento"
    )
    contribution_pct_parent_a = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name="% Contributo Genitore A",
        help_text="Percentuale spese a carico del Genitore A (il resto a carico del B)"
    )

    # ✅ Campo per sovrascrivere l'accordo per questo specifico figlio
    override_split_pct = models.DecimalField(
        "Sovrascrittura % Genitore A",
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Se compilato, sovrascrive la percentuale dell'accordo per questo figlio"
    )
    manual_maintenance_amount = models.DecimalField(
        "Importo mantenimento manuale",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Importo mensile se non è presente una sentenza attiva"
    )

    # children/models.py - SOSTITUISCI la property effective_maintenance_amount
    @property
    def effective_maintenance_amount(self):
        """Priorità: 1. ChildSupport attivo → 2. Manuale (legacy) → 3. None"""
        from django.db.models import Q
        from datetime import date
        if not self.pk:
            return self.manual_maintenance_amount

        today = date.today()
        active_support = self.supports.filter(
            start_date__lte=today,
            is_active=True
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).first()

        if active_support:
            return active_support.amount

        # Fallback legacy (campo manuale sul profilo)
        if self.manual_maintenance_amount:
            return self.manual_maintenance_amount

        return None

    @property
    def age(self):
        today = date.today()
        return (
                today.year
                - self.birth_date.year
                - (
                        (today.month, today.day)
                        < (self.birth_date.month, self.birth_date.day)
                )
        )

    @property
    def effective_maintenance_split_pct(self):
        """Restituisce la % valida per il mantenimento attivo"""
        from datetime import date
        today = date.today()

        support = self.supports.filter(
            start_date__lte=today, is_active=True
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).first()

        # 1. Se il mantenimento ha % specifica → usa quella
        if support and support.split_pct_parent_a is not None:
            return support.split_pct_parent_a
        # 2. Altrimenti fallback su profilo
        return self.contribution_pct_parent_a or Decimal('50.00')

    @property
    def effective_split_pct_parent_a(self):
        # 1. Valore manuale diretto (quello che editi nel formset)
        if self.contribution_pct_parent_a is not None:
            return self.contribution_pct_parent_a
        # 2. Override specifico (se usato in futuro)
        if self.override_split_pct is not None:
            return self.override_split_pct
        # 3. Accordo attivo
        agreement = self.family.support_agreements.filter(is_active=True).first()
        if agreement:
            return agreement.split_pct_parent_a
        # 4. Fallback ultimo resort
        return Decimal('50.00')

    is_active = models.BooleanField(default=True)

    version = models.PositiveIntegerField(default=1)

    previous_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_versions"
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_children"
    )

    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_children"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # ✅ Capitalizza prima lettera di nome e cognome
        return f"{self.name.capitalize()} {self.surname.capitalize()}"

class ChildSupport(models.Model):
    child = models.ForeignKey(
        "ChildProfile",
        on_delete=models.CASCADE,
        related_name="supports"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # ✅ NUOVO CAMPO (opzionale, sovrascrive il profilo se compilato)
    split_pct_parent_a = models.DecimalField(
        "Ripartizione Genitore A",
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Se compilato, sovrascrive la % del profilo per questo mantenimento"
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    # 🔥 VERSIONING
    previous_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_versions"
    )

    version = models.PositiveIntegerField(default=1)

    # 📦 SOFT DELETE (coerente con Expense)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.child.name.capitalize()} - {self.amount} € (v{self.version})"