from .models import FamilyMember
from families.models import FamilyMember
from core.choices import RoleChoices

from families.models import FamilyMember

# families/context_processors.py
def family_membership(request):
    if not request.user.is_authenticated:
        return {}

    from families.models import FamilyMember
    membership = FamilyMember.objects.select_related("family").filter(user=request.user).first()
    family_display_name = membership.family.name if membership and membership.family else None

    # ✅ Controllo setup_complete robusto (funziona con o senza related_name)
    profile = getattr(request.user, 'profile', None) or getattr(request.user, 'userprofile', None)
    is_setup_complete = bool(profile and profile.setup_complete)

    return {
        "membership": membership,
        "family_display_name": family_display_name,
        "is_setup_complete": is_setup_complete,  # 🔑 Nuova variabile globale
    }


# families/context_processors.py



def lawyer_nav_context(request):
    """Inietta automaticamente le famiglie assegnate nel menu di ogni template avvocato."""
    if not request.user.is_authenticated:
        return {'lawyer_nav_families': []}

    # Verifica se l'utente ha un profilo e un ruolo da avvocato
    if hasattr(request.user, 'profile') and request.user.profile.role in RoleChoices.lawyer_roles():
        memberships = FamilyMember.objects.filter(
            user=request.user,
            role__in=RoleChoices.lawyer_roles()
        ).select_related('family')

        families = []
        for m in memberships:
            expected = RoleChoices.PARENT_A if m.role == RoleChoices.LAWYER_A else RoleChoices.PARENT_B
            client_fm = FamilyMember.objects.filter(
                family=m.family, role=expected
            ).select_related('user').first()

            families.append({
                'membership': m,
                'family': m.family,
                'client': client_fm.user if client_fm else None,
            })
        return {'lawyer_nav_families': families}

    return {'lawyer_nav_families': []}