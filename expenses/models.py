from django.conf import settings
from django.db import models
from django.utils import timezone


class ExpenseCategoryGroup(models.Model):

    code = models.CharField(
        max_length=50,
        unique=True
    )

    label = models.CharField(
        max_length=100
    )

    color = models.CharField(
        max_length=7,
        default="#6c757d"
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


class ExpenseCategory(models.Model):

    group = models.ForeignKey(
        ExpenseCategoryGroup,
        on_delete=models.PROTECT,
        related_name="categories"
    )

    slug = models.SlugField(max_length=100)

    display_name = models.CharField(max_length=255)

    color = models.CharField(max_length=7)

    is_active = models.BooleanField(default=True)

    # VERSIONING
    version = models.PositiveIntegerField(default=1)

    previous_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="new_versions"
    )

    valid_from = models.DateTimeField(default=timezone.now)

    valid_to = models.DateTimeField(
        null=True,
        blank=True
    )

    # AUDIT
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_categories"
    )

    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modified_categories"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["group__label", "display_name"]

    def __str__(self):
        return self.display_name

class ExpenseCategoryHistory(models.Model):
    ACTIONS = [
        ("created", "Creata"),
        ("updated", "Modificata"),
        ("deleted", "Disattivata"),
    ]

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.CASCADE,
        related_name="history"
    )

    action = models.CharField(max_length=20, choices=ACTIONS)

    old_name = models.CharField(max_length=255, blank=True)

    new_name = models.CharField(max_length=255, blank=True)

    old_color = models.CharField(max_length=20, blank=True)

    new_color = models.CharField(max_length=20, blank=True)

    changed_at = models.DateTimeField(auto_now_add=True)

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-changed_at"]

class Expense(models.Model):
    # 🎯 SCELTE (raggruppate in cima)
    STATUS_CHOICES = [
        ("pending", "In Sospeso"),
        ("accepted", "Accettata"),
        ("rejected", "Rifiutata"),
        ("paid", "Pagata"),
    ]

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        indexes = [models.Index(fields=["status", "is_active"])]


    category_name_snapshot = models.CharField("Nome categoria", max_length=255, blank=True, default="")
    category_color_snapshot = models.CharField("Colore categoria", max_length=7, blank=True, default="#6f42c1")
    group_snapshot = models.CharField("Gruppo categoria", max_length=100, blank=True, default="ordinarie")



    # 🌐 RELAZIONI CORE
    family = models.ForeignKey("families.Family", on_delete=models.CASCADE, related_name="expenses")
    child = models.ForeignKey("children.ChildProfile", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="expenses")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_expenses")
    expense_type = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")

    # 💰 DATI FINANZIARI
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # ✅ Questo campo salva la percentuale applicata AL MOMENTO della spesa
    split_percentage_a = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="% caricata sul Genitore A per questa spesa (se nulla, usa quella del figlio)"
    )

    description = models.TextField(blank=True, default="")
    expense_date = models.DateField()

    # ✅ WORKFLOW & APPROVAZIONI (FK invece di Boolean)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    approved_by_parent_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_expenses_a"
    )
    approved_by_parent_b = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_expenses_b"
    )

    # 🔄 VERSIONING
    version = models.PositiveIntegerField(default=1)
    previous_version = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="new_versions"
    )

    # 📊 METADATI & AUDIT
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="Archiviata il")
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="modified_expenses", verbose_name="Ultima modifica da"
    )

    # 📊 SNAPSHOT PERCENTUALE (immutabile per versione)
    effective_split_pct_a = models.DecimalField(
        "Quota Genitore A (snapshot)",
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Percentuale effettiva applicata a questa versione"
    )

    def save(self, *args, **kwargs):
        if self.expense_type and not self.pk:  # Solo alla CREAZIONE (pk è None)
            self.category_name_snapshot = self.expense_type.display_name
            self.category_color_snapshot = self.expense_type.color
            self.group_snapshot = self.expense_type.group
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Spesa v{self.version} - {self.amount}€ ({self.child.name})"




    @property
    def amount_parent_a(self):
        """Calcola quanto deve pagare il Genitore A"""
        # Se è stata specificata una % sulla spesa, usa quella.
        # Altrimenti, usa la % di default del profilo figlio.
        pct = self.split_percentage_a
        if pct is None:
            pct = self.child.contribution_pct_parent_a

        return (self.amount * pct) / 100

    @property
    def amount_parent_b(self):
        return self.amount - self.amount_parent_a

    @property
    def is_editable(self):
        """Modificabile se: pending, rejected, o accepted ma non ancora approvata da entrambi."""
        if self.status in ("pending", "rejected"):
            return True
        if self.status == "paid":
            return False
        # Se accepted, è modificabile solo se manca almeno un'approvazione
        return not (self.approved_by_parent_a and self.approved_by_parent_b)

    @property
    def payment_state(self):
        """Stato di pagamento DERIVATO automaticamente. Elimina `payment_state` per evitare incongruenze."""
        if self.status == "paid":
            return "paid"
        if self.status == "accepted" and self.approved_by_parent_b:
            return "partial"
        return "unpaid"

    def get_status_label(self):
        """Restituisce l'etichetta italiana dello stato (fallback sicuro)"""
        labels = {
            "pending": "In Sospeso",
            "accepted": "Accettata",
            "paid": "Pagata",
            "rejected": "Rifiutata"
        }
        return labels.get(self.status, self.status)

    def __str__(self):
        type_name = self.expense_type.display_name if self.expense_type else "Spesa"
        return f"{type_name} - €{self.amount} ({self.get_status_display()})"




'''

creare pagina HTML STORICO
Expense.objects.filter(
    family=family,
    is_active=True
)

Expense.objects.filter(
    family=family
).order_by("-created_at")


Query futura per vedere tutte le spese relative, in questo esempio legali
    Expense.objects.filter(
    family=family,
    expense_type="legal"
)
    '''