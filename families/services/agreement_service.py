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

        # ✅ Evita duplicati usando linked_id e source
        if not CalendarEvent.objects.filter(
                family=family,
                linked_id=agreement.id,
                source="child_support",
                start_time__year=event_date.year,
                start_time__month=event_date.month
        ).exists():
            CalendarEvent.objects.create(
                family=family,
                title=title,
                description=f"Rif. Sentenza: {agreement.decree_number}\nImporto totale: €{agreement.monthly_amount}",
                start_time=start_dt,
                end_time=end_dt,
                event_type="support",
                is_auto_generated=True,
                created_by=agreement.modified_by or family.members.first().user,
                is_shared=True,
                source="child_support",
                linked_id=agreement.id
            )
            created_count += 1

        current_date += relativedelta(months=1)

    return created_count


def generate_spouse_support_calendar_events(agreement):
    """
    Genera eventi mensili di mantenimento coniuge per i prossimi 12 mesi
    e li sincronizza con Google Calendar in modo asincrono.
    """
    from calendar_app.models import CalendarEvent
    from datetime import datetime, date
    from django.utils import timezone
    from dateutil.relativedelta import relativedelta
    import calendar

    family = agreement.family
    beneficiary_name = agreement.beneficiary.get_full_name() if agreement.beneficiary else "Coniuge"
    title = f"💶 Mantenimento Coniuge: {beneficiary_name}"

    # Calcola giorno sicuro (evita 31 febbraio, ecc.)
    safe_day = min(agreement.payment_day, 28)

    current_date = agreement.start_date
    end_date = agreement.end_date  # Obbligatoria per coniuge

    # Genera solo per i prossimi 12 mesi per non appesantire il DB
    horizon = date.today() + relativedelta(months=12)
    limit_date = min(end_date, horizon)

    created_count = 0
    created_event_ids = []  # ✅ Traccia gli ID per sync Google

    while current_date <= limit_date:
        # Adatta il giorno al mese corrente
        max_day = calendar.monthrange(current_date.year, current_date.month)[1]
        day = min(agreement.payment_day, max_day)

        event_date = current_date.replace(day=day)
        start_dt = timezone.make_aware(datetime.combine(event_date, datetime.min.time().replace(hour=9)))
        end_dt = timezone.make_aware(datetime.combine(event_date, datetime.min.time().replace(hour=18)))

        # ✅ Evita duplicati usando linked_id e source
        if not CalendarEvent.objects.filter(
                family=family,
                linked_id=agreement.id,
                source="spouse_support",
                start_time__year=event_date.year,
                start_time__month=event_date.month
        ).exists():
            new_event = CalendarEvent.objects.create(
                family=family,
                title=title,
                description=f"Rif. Sentenza: {agreement.decree_number}\nImporto mensile: €{agreement.monthly_amount}\nBeneficiario: {beneficiary_name}",
                start_time=start_dt,
                end_time=end_dt,
                event_type="support",
                is_auto_generated=True,
                created_by=agreement.modified_by or family.members.first().user,
                is_shared=True,
                source="spouse_support",
                linked_id=agreement.id
            )
            created_count += 1
            created_event_ids.append(new_event.id)

            # ✅ AVVIA SYNC ASINCRONO CON GOOGLE CALENDAR
            try:
                from calendar_app.tasks import sync_event_to_google_task
                sync_event_to_google_task.delay(new_event.id)
                print(f"  📅 Task Celery avviato per evento coniuge {new_event.id}")
            except Exception as e:
                print(f"  ⚠️ Errore avvio task Celery per evento {new_event.id}: {e}")

        current_date += relativedelta(months=1)

    # ✅ SYNC ASINCRONO CON GOOGLE CALENDAR
    if created_event_ids:
        try:
            from calendar_app.tasks import sync_event_to_google_task
            for event_id in created_event_ids:
                sync_event_to_google_task.delay(event_id)
            print(f"📅 Avviata sincronizzazione Google per {len(created_event_ids)} eventi coniuge")
        except Exception as e:
            # Non bloccare se Celery non è disponibile
            print(f"⚠️ Sync Google non avviato (Celery non disponibile): {e}")

    return created_count


def cleanup_spouse_support_calendar_events(agreement):
    """
    Elimina eventi calendario (locali e Google) dopo la data di fine mantenimento.
    """
    from calendar_app.models import CalendarEvent
    from datetime import date

    family = agreement.family

    # ✅ Recupera gli eventi da eliminare (per cleanup Google)
    events_to_delete = list(
        CalendarEvent.objects.filter(
            family=family,
            linked_id=agreement.id,
            source="spouse_support",
            start_time__date__gt=agreement.end_date
        ).values_list('id', flat=True)
    )

    # ✅ Elimina eventi locali
    deleted_count, _ = CalendarEvent.objects.filter(
        family=family,
        linked_id=agreement.id,
        source="spouse_support",
        start_time__date__gt=agreement.end_date
    ).delete()

    # ✅ ELIMINAZIONE ASINCRONA DA GOOGLE CALENDAR
    if events_to_delete:
        try:
            from calendar_app.services.google_calendar_service import cleanup_future_events_from_google
            from calendar_app.models import GoogleCalendarToken

            # Per ogni membro con Google Calendar collegato, elimina eventi futuri
            tokens = GoogleCalendarToken.objects.filter(
                user__family_memberships__family=family,
                is_active=True
            ).select_related('user')

            for token in tokens:
                try:
                    result = cleanup_future_events_from_google(
                        user=token.user,
                        family=family,
                        end_date=agreement.end_date,
                        source_filter='spouse_support'
                    )
                    print(f"🗑️ Eliminati {result['stats']['deleted']} eventi Google coniuge per {token.user.email}")
                except Exception as e:
                    print(f"⚠️ Errore cleanup Google per {token.user.email}: {e}")
        except Exception as e:
            print(f"⚠️ Cleanup Google non disponibile: {e}")

    return deleted_count