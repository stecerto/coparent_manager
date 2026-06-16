from families.utils import get_family_of_user


def can_access_document(user, document, request=None):
    """Verifica se un utente può accedere a un documento specifico"""

    # 1. ✅ FIX: Passa request per recupero corretto della famiglia attiva
    family = get_family_of_user(user, request=request)

    if not family:
        return False

    # 2. Se il documento è condiviso, tutti i membri della famiglia possono vederlo
    if document.scope == "shared":
        return family.members.filter(user=user).exists()

    # 3. Se è privato, può vederlo solo il proprietario
    if document.owner == user:
        return True

    # 4. ✅ LOGICA AVVOCATO: L'avvocato può vedere i documenti privati del suo assistito
    if hasattr(document.owner, 'family_memberships'):
        owner_membership = document.owner.family_memberships.filter(family=family).first()
        if owner_membership:
            expected_role = "lawyer_a" if owner_membership.role == "parent_a" else "lawyer_b"
            return family.members.filter(user=user, role=expected_role).exists()

    return False

def can_edit_document(user, document):
    if document.status in [ "signed", "locked"]:
        return False
    return document.owner == user