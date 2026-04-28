from django.utils import timezone

from children.models import ChildProfile
from utils import get_user_profile


def archive_child(child: ChildProfile, modified_by_user):
    """Marca un figlio come archiviato senza cancellarlo"""
    child.is_active = False
    child.archived_at = timezone.now()
    child.modified_by = modified_by_user
    child.save()
    return child


# =========================
# FIGLI
# =========================
def get_active_children(user):
    """Restituisce la lista dei figli attivi dell'utente"""
    family = get_user_profile(user)

    return family.children.filter(is_active=True)
