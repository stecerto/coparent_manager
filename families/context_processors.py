from .models import FamilyMember
from families.models import FamilyMember
from core.choices import RoleChoices

from families.models import FamilyMember

# families/context_processors.py
def family_membership(request):
    """Inietta contesto famiglia SOLO quando esplicitamente richiesto o per i genitori."""
    if not request.user.is_authenticated:
        return {}

    # 1️⃣ Priorità assoluta: Sessione o URL (contesto esplicito)
    active_id = request.session.get('active_family_id') or request.GET.get('family_id')
    if active_id:
        from families.models import FamilyMember
        mem = FamilyMember.objects.filter(user=request.user, family_id=active_id).select_related('family').first()
        if mem:
            return {
                "active_family": mem.family,
                "active_family_name": mem.family.name,
                "active_role_label": mem.get_role_display(),
                "membership": mem,
            }

    # 2️⃣ Blocchi automatici per ruoli professionali
    profile = getattr(request.user, 'profile', None)
    professional_roles = ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']
    if profile and profile.role in professional_roles:
        # ✅ Nessun fallback: l'avvocato vede la famiglia SOLO dopo aver cliccato "Entra nel contesto"
        return {}

    # 3️⃣ Fallback sicuro per i genitori (UX ottimale)
    from families.models import FamilyMember
    mem = FamilyMember.objects.filter(user=request.user).order_by('-is_primary', '-joined_at').first()
    if mem:
        return {
            "active_family": mem.family,
            "active_family_name": mem.family.name,
            "active_role_label": mem.get_role_display(),
            "membership": mem,
        }

    return {}


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


from families.utils import get_family_of_user
from families.models import FamilyMember

#Inietta automaticamente le variabili in ogni template.
def family_context(request):
    """
    Inietta automaticamente famiglia e ruolo in TUTTI i template.
    Zero modifiche alle view esistenti. Fallback sicuro su valori vuoti.
    """
    # ✅ Valori di default (garantiscono che il template non crashi mai)
    ctx = {
        'active_family': None,
        'active_family_name': '',
        'active_family_membership': None,
        'active_role_label': '',
        'active_is_parent_a': False,
        'active_is_lawyer_a': False,
        'is_setup_complete': False,
    }

    if not request.user.is_authenticated:
        return ctx

    user = request.user
    profile = getattr(user, 'profile', None)
    if profile:
        ctx['is_setup_complete'] = getattr(profile, 'setup_complete', False)
        # Fallback: considera completo se ha almeno nome+cognome+telefono
        if not ctx['is_setup_complete']:
            has_basic = all([
                getattr(profile, 'first_name', None),
                getattr(profile, 'last_name', None),
                getattr(profile, 'phone', None)
            ])
            if has_basic:
                ctx['is_setup_complete'] = True
    # ✅ Usa la tua utility esistente (legge ?family_id o sessione)
    family = get_family_of_user(user, request=request)
    if not family:
        return ctx

    membership = FamilyMember.objects.filter(
        family=family, user=user
    ).select_related('user').first()

    if membership:
        ctx['active_family'] = family
        ctx['active_family_name'] = family.name
        ctx['active_family_membership'] = membership

        role_raw = getattr(membership.role, 'value', membership.role)
        ctx['active_role_label'] = str(role_raw).replace('_', ' ').title()
        ctx['active_is_parent_a'] = membership.role == "parent_a"
        ctx['active_is_lawyer_a'] = membership.role == "lawyer_a"

    return ctx