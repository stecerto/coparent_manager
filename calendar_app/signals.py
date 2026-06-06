# calendar_app/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import EventReminder

@receiver(post_save, sender='calendar_app.CalendarEvent')
def auto_create_reminders(sender, instance, created, **kwargs):
    """Crea promemodi automatici per nuovi eventi manuali"""
    if not created or instance.is_auto_generated:
        return

    now = timezone.now()
    offsets = [timedelta(days=1), timedelta(hours=1)]
    for offset in offsets:
        remind_time = instance.start_time - offset
        if remind_time > now:
            EventReminder.objects.get_or_create(
                event=instance,
                remind_at=remind_time,
                defaults={'sent': False}
            )