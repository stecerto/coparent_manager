from django.utils import timezone
from children.models import ChildProfile


def create_child(family, user, data):
    return ChildProfile.objects.create(
        family=family, modified_by=user,
        name=data.get("name"), surname=data.get("surname"),
        birth_date=data.get("birth_date"),
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
from children.models import ChildSupport


def update_child_support(child, new_amount, start_date):

    # 👉 prendi mantenimento attivo
    current = ChildSupport.objects.filter(
        child=child,
        is_active=True,
        end_date__isnull=True
    ).order_by("-start_date").first()

    if current:
        # chiudi il vecchio
        current.end_date = start_date
        current.is_active = False
        current.save()

        # crea nuova versione
        new_support = ChildSupport.objects.create(
            child=child,
            amount=new_amount,
            start_date=start_date,
            previous_version=current,
            version=current.version + 1
        )
    else:
        new_support = ChildSupport.objects.create(
            child=child,
            amount=new_amount,
            start_date=start_date
        )

    return new_support


def archive_child(child, user):
    child.is_active = False
    child.archived_at = timezone.now()
    child.archived_by = user
    child.save()

    return child