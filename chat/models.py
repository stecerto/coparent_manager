from django.conf import settings
from django.db import models

from families.models import Family
from calendar_app.models import CalendarEvent


class FamilyMessage(models.Model):
    family = models.ForeignKey("families.Family", on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="received_messages")
    # NUOVO → risposta
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies"
    )

    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # -----------------------------
    # VERSIONING
    # -----------------------------
    is_active = models.BooleanField(default=True)
    previous_version = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="new_versions")
    version = models.PositiveIntegerField(default=1)
    # VERSIONING

    edited_at = models.DateTimeField(null=True, blank=True)

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_messages"
    )

    deleted_at = models.DateTimeField(null=True, blank=True)

    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_family_messages"
    )

    # LINK EVENTO
    linked_event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_messages"
    )

    def __str__(self):
        return f"{self.sender.username} ({self.created_at}): {self.content[:30]}"

class PrivateMessage(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_private_messages"
    )

    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_private_messages"
    )

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE
    )

    content = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

class MessageAttachment(models.Model):
    message = models.ForeignKey(
        "FamilyMessage",
        on_delete=models.CASCADE,
        related_name="attachments"
    )
    file = models.FileField(upload_to="message_attachments/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name

