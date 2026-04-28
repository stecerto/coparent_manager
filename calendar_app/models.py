# calendar_app/models.py
from django.db import models
from django.conf import settings

from children.models import ChildProfile
from documents.models import Document
from families.models import Family


class CalendarEvent(models.Model):
    EVENT_TYPES = [
        ("custody", "Affidamento"),
        ("school", "Scuola"),
        ("medical", "Medico"),
        ("expense", "Spesa"),
        ("legal", "Legale"),
        ("other", "Altro"),
    ]

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="calendar_events"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    children = models.ManyToManyField(
        ChildProfile,
        blank=True,
        related_name="calendar_events"
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        default="other"
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    is_shared = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    previous_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_versions"
    )

    version = models.PositiveIntegerField(default=1)

    archived_at = models.DateTimeField(
        null=True,
        blank=True
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_calendar_events"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

class EventReminder(models.Model):   #dobbiamo useare Celery  @shared_task  def send_event_reminder():
    event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE
    )

    remind_at = models.DateTimeField()

    sent = models.BooleanField(default=False)

class EventComment(models.Model):
    event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name="comments"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_event_calendar"
    )

    updated_at = models.DateTimeField(auto_now=True)

class EventAttachment(models.Model):
    event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE
    )
