from families.utils import get_family_of_user


def can_access_document(user, document):
    family = get_family_of_user(user)

    if not family:
        return False

    if document.family != family:
        return False

    if document.scope == "shared":
        return True

    membership = family.memberships.filter(user=user).first()

    if not membership:
        return False

    role = membership.role
    # proprietario sempre può
    if document.owner == user:
        return True
    # avvocato A → privati parent_a
    if role == "lawyer_a":
        return document.owner.memberships.filter(
            family=family,
            role="parent_a"
        ).exists()
    # avvocato B → privati parent_b
    if role == "lawyer_b":
        return document.owner.memberships.filter(
            family=family,
            role="parent_b"
        ).exists()

    return False

def can_edit_document(user, document):
    if document.status in [ "signed", "locked"]:
        return False
    return document.owner == user