from django import template
from families.models import FamilyMember

register = template.Library()


@register.filter
def parent_display_name(family, role):
    """
    Restituisce il nome reale del genitore se registrato, altrimenti 'Genitore A/B'.
    Uso: {{ family|parent_display_name:"parent_a" }}
    """
    if not family:
        return "Genitore A" if role == "parent_a" else "Genitore B"

    role_map = {
        'parent_a': ['parent_a'],
        'parent_b': ['parent_b'],
    }

    allowed_roles = role_map.get(role, [role])

    member = FamilyMember.objects.filter(
        family=family,
        role__in=allowed_roles,
        user__is_active=True
    ).select_related('user').first()

    if member and member.user:
        full_name = member.user.get_full_name().strip()
        if full_name:
            return full_name
        return member.user.email

    return "Genitore A" if role == "parent_a" else "Genitore B"


@register.filter
def parent_short_name(family, role):
    """
    Versione breve: restituisce solo il nome o iniziale.
    """
    full_name = parent_display_name(family, role)

    if full_name.startswith("Genitore"):
        return full_name

    return full_name.split()[0] if full_name else full_name