from django.utils import timezone

from children.models import ChildProfile
from accounts.utils import get_user_profile


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


def get_child_split_pct(child):
    """
    Restituisce la percentuale di ripartizione per un figlio.
    Priorità: contribution_pct_parent_a → fallback a 50.00
    """
    if child and child.contribution_pct_parent_a is not None:
        return float(child.contribution_pct_parent_a)
    return 50.00  # Fallback sicuro


def calculate_expense_shares(child, amount):
    """
    Calcola le quote di una spesa dato l'importo e il figlio.
    Returns: (quota_a, quota_b) come float arrotondati a 2 decimali
    """
    pct_a = get_child_split_pct(child)
    pct_b = 100.0 - pct_a