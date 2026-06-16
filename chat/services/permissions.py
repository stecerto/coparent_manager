# chat/services/permissions.py
from families.utils import get_user_role_in_family
from django.db.models import Q
from chat.models import FamilyMessage

def get_accessible_threads_for_user(user, family):
    """Restituisce la lista di thread_type accessibili all'utente."""
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
        # ✅ FIX FASE C: I lawyer devono poter accedere a legal_a e legal_b.
        # La sicurezza reale (chi vede i messaggi di chi) è garantita
        # dal filtro Q(sender=user) | Q(recipient=user) in get_visible_messages.
        allowed_types.extend([
            'legal_a', 'legal_b',
            'lawyer_private', 'mediation', 'consulting'
        ])
    elif role_base == 'mediator':
        allowed_types.extend(['mediator_private', 'mediation', 'consulting'])
    elif role_base == 'consultant':
        allowed_types.extend(['consultant_private', 'consulting', 'mediation'])

    return allowed_types


def get_visible_messages(user, family):
    """
    Query ottimizzata: restituisce SOLO i messaggi che l'utente può vedere.
    ✅ FIX FASE C: Usa una singola query con Q objects per evitare union() + distinct().
    """
    from chat.models import Conversation

    allowed_types = get_accessible_threads_for_user(user, family)

    # 1. Recupera gli ID delle Conversation accessibili all'utente
    all_convs = Conversation.objects.filter(family=family, is_active=True)
    accessible_conv_ids = [
        conv.id for conv in all_convs if conv.can_user_access(user)
    ]

    # 2. Query unica combinata: Messaggi "classici" OPPURE Messaggi in "Conversation" accessibili
    return FamilyMessage.objects.filter(
        family=family,
        is_active=True
    ).filter(
        # ✅ CASO 1: Messaggi "classici" (senza Conversation)
        Q(
            conversation__isnull=True,
            thread_type__in=allowed_types
        ) & (
            Q(thread_type='family') |
            Q(thread_type__in=['mediation', 'consulting']) |
            Q(sender=user) |
            Q(recipient=user)
        )
        |  # ✅ OPPURE
        # CASO 2: Messaggi in "Conversation" con permessi granulari
        Q(conversation_id__in=accessible_conv_ids)
    ).distinct().order_by('created_at')

