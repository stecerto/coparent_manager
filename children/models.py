from datetime import date
from django.conf import settings
from django.db import models


class ChildProfile(models.Model):
    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="children"
    )

    name = models.CharField(max_length=255)
    surname = models.CharField(max_length=255)
    birth_date = models.DateField()

    notes = models.TextField(blank=True)

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

    def __str__(self):
        return f"{self.name} {self.surname}"

class ChildSupport(models.Model):
    child = models.ForeignKey(
        "ChildProfile",
        on_delete=models.CASCADE,
        related_name="supports"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)

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
        return f"{self.child.name} - {self.amount} € (v{self.version})"