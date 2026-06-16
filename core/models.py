# Create your models here.
from django import forms
from django.contrib import admin
from django.db import models
from django.utils import timezone
from core.choices import RoleChoices
from families.models import PaymentSubscription


class Payment(models.Model):
    """Storico pagamenti"""

    STATUS_CHOICES = [
        ("pending", "In attesa"),
        ("completed", "Completato"),
        ("failed", "Fallito"),
        ("refunded", "Rimborsato"),
    ]

    # ✅ Corretto: usa PaymentSubscription invece di Subscription
    subscription = models.ForeignKey(
        PaymentSubscription,
        on_delete=models.CASCADE,
        related_name="payments"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    payment_date = models.DateTimeField(default=timezone.now)
    payment_method = models.CharField(max_length=50, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamenti"
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.subscription.user.email} - €{self.amount} ({self.status})"


# ==============================================================================
# ✅ NUOVO MODELLO AGGIUNTO: DashboardWidget
# ==============================================================================
from django.db import models


class DashboardWidget(models.Model):
    """
    Widget dinamici per la dashboard.
    Gestione visibilità per ruoli e piani.
    """

    PLAN_LEVELS = [
        (1, "Starter"),
        (2, "Pro"),
        (3, "Enterprise"),
    ]

    ROLE_CHOICES = [
        ("parent", "Genitore"),
        ("lawyer", "Avvocato"),
        ("mediator", "Mediatore"),
        ("consultant", "Consulente"),
    ]

    title = models.CharField(
        max_length=100,
        verbose_name="Titolo Widget",
        help_text="Es: 'Prossime Scadenze', 'Documenti in Attesa'"
    )

    widget_key = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name="Chiave Widget",
        help_text="Identificativo univoco usato nel template HTML (es. 'upcoming_events')"
    )

    # JSON: lista ruoli
    target_roles = models.JSONField(
        default=list,
        verbose_name="Ruoli Target",
        help_text="Lista di ruoli (base, senza _a/_b) che possono vedere questo widget."
    )

    # JSON: lista piani abilitati
    allowed_plan_levels = models.JSONField(
        default=list,
        verbose_name="Piani Abilitati",
        help_text="Lista dei piani che possono vedere il widget"
    )

    position = models.PositiveIntegerField(
        default=0,
        verbose_name="Posizione",
        help_text="Ordine di visualizzazione nella griglia (0 = primo in alto/a sinistra)"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Attivo",
        help_text="Se disattivato, il widget non verrà renderizzato"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'title']
        verbose_name = "Widget Dashboard"
        verbose_name_plural = "Widget Dashboard"

    def __str__(self):
        roles = ", ".join(self.target_roles) if self.target_roles else "Tutti"

        plan_map = dict(self.PLAN_LEVELS)
        plans = ", ".join(
            plan_map.get(p, str(p)) for p in self.allowed_plan_levels
        ) if self.allowed_plan_levels else "Tutti"

        return f"{self.title} [{roles}] (Piani: {plans})"



    @classmethod
    def get_active_for_role(cls, role: str):
        """
        Restituisce i widget attivi e ordinati per un ruolo specifico.
        ✅ COMPATIBILE CON SQLITE: filtra in Python invece che nel DB.
        """
        base_role = RoleChoices.normalize_role(role)
        if not base_role:
            return []

        # Carica tutti i widget attivi (sono pochi, filtriamo in memoria)
        all_widgets = list(cls.objects.filter(is_active=True))

        # Filtra in Python: il ruolo base deve essere nella lista target_roles
        filtered = [
            w for w in all_widgets
            if w.target_roles and base_role in w.target_roles
        ]

        # Ordina per position
        return sorted(filtered, key=lambda w: w.position)

    @classmethod
    def get_active_for_role_and_plan(cls, role: str, plan_level: int):
        """
        Restituisce i widget attivi per un ruolo specifico E livello piano.
        ✅ COMPATIBILE CON SQLITE: filtra in Python invece che nel DB.
        """
        base_role = RoleChoices.normalize_role(role)
        if not base_role:
            return []

        # Carica tutti i widget attivi con piano compatibile
        all_widgets = list(cls.objects.filter(
            is_active=True,
            allowed_plan_levels=plan_level
        ))

        # Filtra in Python per target_roles
        filtered = [
            w for w in all_widgets
            if w.target_roles and base_role in w.target_roles
        ]

        # Ordina per position
        return sorted(filtered, key=lambda w: w.position)