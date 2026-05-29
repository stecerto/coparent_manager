from django.db import models

# notifications/models.py
from django.db import models
from django.conf import settings


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ("chat_private", "💬 Messaggio Privato"),
        ("expense_pending", "💰 Spesa in Attesa"),
        ("expense_rejected", "🔴 Spesa Rifiutata"),
        ("expense_paid", "✅ Spesa Pagata"),
        ("event_reminder", "📅 Promemoria Evento"),
        ("invite", "📨 Nuovo Invito"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)

    title = models.CharField(max_length=255)
    message = models.TextField()

    # Link opzionale per deep-linking
    target_url = models.CharField(max_length=500, blank=True)
    target_model = models.CharField(max_length=50, blank=True, help_text="Es: 'Expense', 'FamilyMessage'")
    target_id = models.PositiveIntegerField(null=True, blank=True)

    # Metadata flessibile (es. expense_id, family_id, etc.)
    metadata = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False)
    is_sent_email = models.BooleanField(default=False)  # Traccia se email è stata inviata

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.get_notification_type_display()}"