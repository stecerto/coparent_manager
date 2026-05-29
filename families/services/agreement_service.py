# families/services/agreement_service.py
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from calendar_app.models import CalendarEvent
from django.utils import timezone


def generate_support_calendar_events(agreement):
    """Genera eventi mensili di mantenimento per i prossimi 12 mesi"""
    family = agreement.family
    child_names = ", ".join([c.name for c in agreement.children.all()])
    title = f"💶 Mantenimento: {child_names}"

    # Calcola giorno sicuro (evita 31 febbraio, ecc.)
    safe_day = min(agreement.payment_day, 28)

    current_date = agreement.start_date
    end_date = agreement.end_date or (agreement.start_date + relativedelta(years=18))

    # Genera solo per i prossimi 12 mesi per non appesantire il DB
    horizon = date.today() + relativedelta(months=12)
    limit_date = min(end_date, horizon)

    created_count = 0
    while current_date <= limit_date:
        # Adatta il giorno al mese corrente
        import calendar
        max_day = calendar.monthrange(current_date.year, current_date.month)[1]
        day = min(agreement.payment_day, max_day)

        event_date = current_date.replace(day=day)
        start_dt = timezone.make_aware(datetime.combine(event_date, datetime.min.time().replace(hour=9)))
        end_dt = timezone.make_aware(datetime.combine(event_date, datetime.min.time().replace(hour=18)))

        # Evita duplicati
        if not CalendarEvent.objects.filter(
                family=family,
                linked_agreement=agreement,
                start_time__year=event_date.year,
                start_time__month=event_date.month
        ).exists():
            CalendarEvent.objects.create(
                family=family,
                title=title,
                description=f"Rif. Sentenza: {agreement.decree_number}\nImporto totale: €{agreement.monthly_amount}\nGenitore A: {agreement.split_pct_parent_a}% | Genitore B: {100 - float(agreement.split_pct_parent_a)}%",
                start_time=start_dt,
                end_time=end_dt,
                event_type="support",
                is_auto_generated=True,
                linked_agreement=agreement,
                created_by=agreement.modified_by or family.members.first().user,
                is_shared=True,
                source = "agreement",
                linked_id = agreement.id
            )
            created_count += 1

        current_date += relativedelta(months=1)

    return created_count