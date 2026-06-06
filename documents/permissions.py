from django.http import request

from families.models import FamilyMember
from families.utils import get_family_of_user


def can_access_document(user, document):
    """Verifica se un utente può accedere a un documento specifico"""

    # 1. Ottieni la famiglia (senza request usa il fallback, ok per controlli base)
    # Nota: idealmente qui servirebbe la request per la famiglia attiva,
    # ma per i permessi di solito basta verificare l'appartenenza.
    family = get_family_of_user(user)

    if not family:
        return False

    # 2. Se il documento è condiviso, tutti i membri della famiglia possono vederlo
    if document.scope == "shared":
        return family.members.filter(user=user).exists()

    # 3. Se è privato, può vederlo solo il proprietario
    if document.owner == user:
        return True

    # 4. ✅ LOGICA AVVOCATO: L'avvocato può vedere i documenti privati del suo assistito?
    # Qui usiamo family_memberships perché document.owner è un User, non una Family
    if hasattr(document.owner, 'family_memberships'):
        # Controlla se l'utente (avvocato) ha una membership per la famiglia del proprietario (assistito)
        # e se il ruolo è coerente (es. lawyer_a vede parent_a)
        owner_membership = document.owner.family_memberships.filter(family=family).first()
        if owner_membership:
            expected_role = "lawyer_a" if owner_membership.role == "parent_a" else "lawyer_b"
            # Verifica se l'utente corrente ha quel ruolo specifico
            return family.members.filter(user=user, role=expected_role).exists()

    return False

def can_edit_document(user, document):
    if document.status in [ "signed", "locked"]:
        return False
    return document.owner == user