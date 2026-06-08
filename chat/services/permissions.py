# chat/services/permissions.py

def get_accessible_threads_for_user(user, family):
    """Restituisce la lista di thread_type accessibili all'utente."""
    from families.utils import get_user_role_in_family
    role = get_user_role_in_family(user, family)
    role_str = str(role).strip().lower() if role else ''
    role_base = role_str.replace('_a', '').replace('_b', '')

    allowed_types = ['family']  # Tutti vedono la chat famiglia

    if role_base == 'parent':
        allowed_types.extend([
            'legal_a', 'legal_b',
            'mediation_private', 'consultant_private',
            'mediation', 'consulting'
        ])
    elif role_base == 'lawyer':
        allowed_types.extend(['lawyer_private', 'mediation', 'consulting'])
    elif role_base == 'mediator':
        allowed_types.extend(['mediator_private', 'mediation', 'consulting'])
    elif role_base == 'consultant':
        allowed_types.extend(['consultant_private', 'consulting', 'mediation'])

    return allowed_types


def get_visible_messages(user, family):
    """Query ottimizzata: restituisce SOLO i messaggi che l'utente può vedere."""
    from django.db.models import Q
    from chat.models import FamilyMessage

    allowed_types = get_accessible_threads_for_user(user, family)

    return FamilyMessage.objects.filter(
        family=family,
        is_active=True,
        thread_type__in=allowed_types
    ).filter(
        Q(thread_type='family') |
        Q(thread_type__in=['mediation', 'consulting']) |
        Q(sender=user) |
        Q(recipient=user)
    ).distinct().order_by('created_at')

