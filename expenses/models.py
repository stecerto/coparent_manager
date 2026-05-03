from django.conf.locale import fa
from django.db import models
from django.conf import settings


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)  # nome visualizzato (es. "Spesa figlio")
    color = models.CharField(max_length=7, default="#6f42c1")

    def __str__(self):
        return self.display_name


class Expense(models.Model):
    EXPENSE_TYPES = [
        ("child", "Spesa figlio"),
        ("medical", "Spesa medica"),
        ("school", "Scuola"),
        ("extra", "Straordinarie"),
        ("sport", "Sport"),
        ("legal", "Legale"),
        ("stamp_duty", "Marca da bollo"),
        ("lawyer_invoice", "Fattura avvocato"),
        ("abbigliamento", "Abbigliamento"),
        ("ricariche telefono", "Ricarica Telefono"),
        ("other", "Altro"),
    ]

    PAYMENT_CHOICES = [
        ("unpaid", "Da pagare"),
        ("partial", "Parzialmente pagato"),
        ("paid", "Pagato e verificato")
    ]
    payment_status = models.CharField(
        max_length=10, choices=PAYMENT_CHOICES, default="unpaid"
    )

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="expenses"
    )
    child = models.ForeignKey(
        "children.ChildProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_expenses"
    )

    expense_type = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses"
    )


    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    description = models.TextField()

    expense_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    parent_a_share = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50
    )

    parent_b_share = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50
    )

    approved_by_parent_a = models.BooleanField(
        null=True,
        blank=True
    )

    approved_by_parent_b = models.BooleanField(
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)

    STATUS_CHOICES = [
        ("pending", "In Sospeso"),
        ("accepted", "Accettata"),
        ("paid", "Pagata"),
        ("rejected", "Rifiutata"),
    ]

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending"
    )

#VERSIONE VERSIONING
    previous_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_versions"
    )

    version = models.PositiveIntegerField(default=1)

#VERSIONE ARCHIVING SOFT_DELETE
    archived_at = models.DateTimeField(
        null=True,
        blank=True
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_expenses"
    )

    @property
    def is_editable(self):
        """
        Restituisce True se la spesa può essere modificata.
        Regole:
        - Sempre modificabile se 'pending'
        - Modificabile se almeno un genitore non ha ancora approvato
        - Bloccata se 'paid' o se entrambi hanno approvato e status != pending
        """
        if self.status in ("pending", "rejected"): # Rifiutata = si può correggere e riproporre
            return True
        if self.status == "paid":
            return False  # Pagata = bloccata definitivamente
        # Rifiutata = si può correggere e riproporre
        if self.status == "accepted":
            # ✅ Modificabile SOLO se NESSUNO ha accettato (entrambi null o False)
            return not (self.approved_by_parent_a or self.approved_by_parent_b )
        return False

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
        return f"{self.description} - {self.amount}"



'''
class ExpenseDocument(models.Model):
    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="expense_documents"
    )

    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="documents_expense"
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    title = models.CharField(max_length=255)

    file = models.FileField(
        upload_to="expense_documents/"
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    previous_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="old_versions"
    )

    version = models.PositiveIntegerField(default=1)

    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_expenses_documents"
    )



    def __str__(self):
        return self.title





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