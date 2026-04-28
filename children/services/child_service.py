from django.utils import timezone
from children.models import ChildProfile


def create_child(family, user, data):
    return ChildProfile.objects.create(
        family=family,
        name=data.get("name"),
        surname=data.get("surname"),
        birth_date=data.get("birth_date"),
        notes=data.get("notes", ""),
        modified_by=user
    )


def update_child(child, user, data):
    child.is_active = False
    child.archived_at = timezone.now()
    child.archived_by = user
    child.save()

    return ChildProfile.objects.create(
        family=child.family,
        name=data.get("name"),
        surname=data.get("surname"),
        birth_date=data.get("birth_date"),
        notes=data.get("notes", ""),
        version=child.version + 1,
        previous_version=child,
        modified_by=user
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