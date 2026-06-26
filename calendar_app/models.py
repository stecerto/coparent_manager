# calendar_app/models.py
from django.db import models
from django.conf import settings

from children.models import ChildProfile
from documents.models import Document
from families.models import Family

# calendar_app/models.py
from django.db import models
from django.conf import settings
from children.models import ChildProfile
from documents.models import Document
from families.models import Family
from expenses.models import ExpenseCategory, Expense  # ✅ Importa Expense


class ProfessionalEvent(models.Model):
    """Eventi personali per professionisti (avvocati, mediatori, consulenti)"""

    EVENT_TYPES = [
        ("meeting", "👥 Riunione cliente"),
        ("court", "⚖️ Udienza"),
        ("consultation", "💼 Consulenza"),
        ("mediation", "🤝 Mediazione"),
        ("deadline", "📅 Scadenza legale"),
        ("other", "📌 Altro"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="professional_events"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default="other")

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True, help_text="Luogo dell'appuntamento")

    # Link opzionale a una famiglia (se l'evento riguarda una pratica specifica)
    family = models.ForeignKey(
        'families.Family',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="professional_events"
    )

    is_active = models.BooleanField(default=True)
    google_event_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.start_time.strftime('%d/%m/%Y %H:%M')})"


class CalendarEvent(models.Model):
    EVENT_TYPES = [
        ("custody", "🏠 Affidamento / Cambio casa"),
        ("support", "💰 Mantenimento"),
        ("school", "🏫 Scuola / Gita Scolastica"),
        ("medical", "🏥 Medico / Terapia"),
        ("expense", "💰 Spesa / Rimborso"),
        ("legal", "⚖️ Legale / Udienza"),
        ("holiday_a", "🏖️ Ferie Genitore A"),
        ("holiday_b", "🏖️ Ferie Genitore B"),
        ("child_event", "⚽ Evento Figlio (Sport/Compleanno)"),
        ("mediation", "🤝 Riunione Mediazione"),
        ("consulting", "💼 Riunione Consulenza"),
        ("other", "📌 Altro"),
    ]

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="calendar_events")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    children = models.ManyToManyField(ChildProfile, blank=True, related_name="calendar_events")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default="other")

    # ✅ NUOVO: Link opzionale a categoria spesa (coerenza con expenses)
    expense_category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calendar_events",
        help_text="Categoria spesa se l'evento genera una spesa"
    )

    # ✅ NUOVO: Link alla spesa generata automaticamente
    linked_expense = models.ForeignKey(
        Expense,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_events",
        help_text="Spesa generata automaticamente da questo evento"
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    is_shared = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    is_auto_generated = models.BooleanField(default=False)

    source = models.CharField(
        max_length=20,
        choices=[
            ("manual", "📅 Creato manualmente"),
            ("chat", "💬 Generato da Chat"),
            ("expense", "💰 Generato da Spesa"),
            ("agreement", "📄 Generato da Accordo (legacy)"),
            ("child_support", "💰 Mantenimento Figli"),
            ("spouse_support", "💰 Mantenimento Coniuge"),
        ],
        default="manual",
        db_index=True
    )

    linked_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    previous_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_versions"
    )

    version = models.PositiveIntegerField(default=1)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_calendar_events"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    google_event_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="ID evento su Google Calendar (se sincronizzato)"
    )

    def __str__(self):
        return f"{self.title} ({self.start_time.strftime('%d/%m/%Y')})"

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


class GoogleCalendarToken(models.Model):
    """Token OAuth2 per integrazione Google Calendar"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_calendar_token'
    )

    # Token OAuth2
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_uri = models.URLField(default='https://oauth2.googleapis.com/token')
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)

    # Metadati
    scopes = models.TextField(help_text="Scopes separati da spazio")
    expiry = models.DateTimeField(null=True, blank=True)
    calendar_id = models.CharField(
        max_length=255,
        default='primary',
        help_text="ID calendario Google (default: primary)"
    )

    # Stato
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Token Google Calendar"
        verbose_name_plural = "Token Google Calendar"

    def __str__(self):
        return f"Google Calendar - {self.user.email}"

    @property
    def is_expired(self):
        """Verifica se il token è scaduto"""
        if not self.expiry:
            return False
        from django.utils import timezone
        return timezone.now() >= self.expiry