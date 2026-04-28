# families/utils.py

from families.models import FamilyMember, Family

def is_lawyer(user):
    return user.userprofile.role == 'lawyer'


def is_parent(user):
    return user.userprofile.role in ['parent_a', 'parent_b']


def get_user_families(user):
    """
    Restituisce tutte le famiglie collegate a un utente.
    Include:
        - Famiglie dove è membro (Parent A/B o Lawyer A/B)
    """
    return (
        Family.objects
        .filter(members__user=user)
        .distinct()
    )

def get_family_of_user(user):
    """
    Restituisce la famiglia dell'utente che ricopre il ruolo di parent_a o parent_b nella famiglia.
    """
    membership = (
        FamilyMember.objects
        .select_related("family")
        .filter(user=user)
        .first()
    )
    return membership.family if membership else None


def get_family_lawyer(family, lawyer_role="lawyer_a"):
    """
    Restituisce l'utente che ricopre il ruolo di lawyer_a o lawyer_b nella famiglia.
    """
    member = family.members.filter(role=lawyer_role).first()
    return member.user if member else None


def get_family_members_by_role(family, role):
    """
    Restituisce la lista dei membri di una famiglia con un ruolo specifico
    """
    return family.members.filter(role=role)

def get_family_parent(family, role="parent_a"):
    member = family.members.filter(role=role).first()
    return member.user if member else None

def get_user_role_in_family(user):
    membership = user.family_memberships.first()
    return membership.role if membership else None