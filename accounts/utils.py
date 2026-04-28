# accounts/utils.py
from accounts.models import UserProfile
from children.models import ChildProfile
from families.models import Family, FamilyMember, Invitation
from django.utils import timezone


# =========================
# UTENTE / PROFILO
# =========================
def get_user_profile(user):
    """Restituisce il profilo dell'utente, crea se non esiste"""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def is_setup_complete(user):
    """Controlla se l'utente ha completato il setup"""
    profile = get_user_profile(user)
    return profile.setup_complete




