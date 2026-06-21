from django.contrib.auth.decorators import login_required
from django.utils import timezone
from psycopg import transaction

from children.models import ChildProfile

from django.utils import timezone
from django.core.exceptions import ValidationError
from children.models import ChildProfile


def create_child(family, user, data):
    """
    Crea un nuovo figlio con controllo duplicati.
    Un figlio è considerato duplicato se ha stesso nome+cognome+data_nascita nella stessa famiglia.
    """
    name = data.get("name", "").strip()
    surname = data.get("surname", "").strip()
    birth_date = data.get("birth_date")

    # ✅ CONTROLLO DUPLICATI: cerca figlio attivo con stessi dati
    if name and surname and birth_date:
        existing = ChildProfile.objects.filter(
            family=family,
            name=name,
            surname=surname,
            birth_date=birth_date,
            is_active=True
        ).first()

        if existing:
            # Se esiste già, ritorna l'esistente invece di crearne uno nuovo
            # Opzionalmente puoi aggiornare i dati se sono cambiati
            return existing

    # Crea nuovo figlio solo se non esiste duplicato
    return ChildProfile.objects.create(
        family=family,
        modified_by=user,
        name=name,
        surname=surname,
        birth_date=birth_date,
        custody_type=data.get("custody_type", "shared_custody"),
        contribution_pct_parent_a=data.get("contribution_pct_parent_a"),
        manual_maintenance_amount=data.get("manual_maintenance_amount"),
        override_split_pct=data.get("override_split_pct"),
        notes=data.get("notes", "")
    )

def update_child(child, user, data):
    child.is_active = False
    child.archived_at = timezone.now()
    child.archived_by = user
    child.save()

    return ChildProfile.objects.create(
        family=child.family, modified_by=user,
        name=data.get("name"), surname=data.get("surname"),
        birth_date=data.get("birth_date"),
        custody_type=data.get("custody_type", "shared_custody"),
        contribution_pct_parent_a=data.get("contribution_pct_parent_a"),
        manual_maintenance_amount=data.get("manual_maintenance_amount"),
        override_split_pct=data.get("override_split_pct"),
        notes=data.get("notes", ""),
        version=child.version + 1,
        previous_version=child
    )


from datetime import date
from django.db import transaction
from children.models import ChildSupport


def update_child_support(child, new_amount, start_date, end_date=None, payer_role='parent_a', split_pct_parent_a=50.00):
    """
    Aggiorna il mantenimento di un figlio:
    1. Chiude il mantenimento attivo precedente
    2. Crea un nuovo record
    3. Genera eventi calendario per l'anno in corso
    4. Se end_date è cambiato, elimina eventi futuri
    """
    with transaction.atomic():
        # 👉 prendi mantenimento attivo (DEVE essere UN SOLO)
        current = ChildSupport.objects.filter(
            child=child,
            support_type='child',
            is_active=True,
        ).order_by("-start_date", "-created_at").first()  # ✅ Ordina anche per created_at

        # ✅ DEBUG
        print(f"🔍 DEBUG update_child_support:")
        print(f"  Figlio: {child.name}")
        print(f"  Importo: €{new_amount}")
        print(f"  Payer: {payer_role}")
        print(f"  Current found: {current.id if current else 'None'}")

        # ✅ Se esiste un record attivo, chiudilo PRIMA di creare il nuovo
        if current:
            print(f"  ✅ Chiudo record precedente ID={current.id}")
            current.end_date = start_date
            current.is_active = False
            current.save(update_fields=['end_date', 'is_active'])

            # ✅ Verifica che sia stato salvato
            current.refresh_from_db()
            print(f"  ✅ Verifica: is_active={current.is_active}")

            # Crea nuova versione
            new_support = ChildSupport.objects.create(
                child=child,
                family=child.family,
                support_type='child',
                amount=new_amount,
                start_date=start_date,
                end_date=end_date,
                payer_role=payer_role,
                split_pct_parent_a=split_pct_parent_a,
                previous_version=current,
                version=current.version + 1,
                is_active=True,
            )
        else:
            print(f"  ℹ️ Nessun record precedente, creo nuovo")
            new_support = ChildSupport.objects.create(
                child=child,
                family=child.family,
                support_type='child',
                amount=new_amount,
                start_date=start_date,
                end_date=end_date,
                payer_role=payer_role,
                split_pct_parent_a=split_pct_parent_a,
                is_active=True,
            )

        print(f"  ✅ Creato nuovo record ID={new_support.id}")

        # 📅 Genera eventi calendario
        from calendar_app.services.calendar_service import generate_child_support_calendar_events
        generate_child_support_calendar_events(new_support)

        return new_support


def archive_child(child, user):
    child.is_active = False
    child.archived_at = timezone.now()
    child.archived_by = user
    child.save()

    return child