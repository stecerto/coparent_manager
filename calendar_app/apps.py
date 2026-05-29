# calendar_app/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class CalendarAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "calendar_app"

    def ready(self):
        # ✅ Import sicuro con fallback
        try:
            import calendar_app.signals  # noqa: F401
        except Exception as e:
            logger.warning(f"⚠️ Segnali calendar_app non caricati: {e}")