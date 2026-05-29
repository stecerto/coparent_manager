# families/utils.py

from families.models import FamilyMember, Family


# families/utils.py

def generate_family_name(parent_user, suffix=None):
    """
    Genera un nome famiglia univoco e leggibile.
    Formato: "Famiglia [Cognome] [Nome] [Anno]"
    Esempio: "Famiglia Rossi Mario 1985"
    """
    # 1. Cognome (obbligatorio)
    cognome = parent_user.last_name.strip() if parent_user.last_name else "SenzaCognome"

    # 2. Nome (opzionale, ma utile)
    nome = parent_user.first_name.strip() if parent_user.first_name else ""

    # 3. Anno di nascita o telefono come discriminante (opzionale)
    # Priorità: birth_date > phone > suffix generico
    discriminante = ""
    if hasattr(parent_user, 'profile'):
        profile = parent_user.profile
        if profile.birth_date:
            discriminante = str(profile.birth_date.year)
        elif profile.phone:
            # Usa ultime 4 cifre del telefono per privacy
            discriminante = profile.phone.replace(" ", "").replace("-", "")[-4:]

    if not discriminante and suffix:
        discriminante = str(suffix)

    # Costruisci il nome finale
    parts = ["Famiglia", cognome]
    if nome:
        parts.append(nome)
    if discriminante:
        parts.append(f"({discriminante})")  # Parentesi per leggibilità

    return " ".join(parts)


def is_lawyer(user):
    profile = getattr(user, "userprofile", None)

    if not profile:
        return False

    return profile.role in ["lawyer_a", "lawyer_b"]


def is_parent(user):
    profile = getattr(user, "userprofile", None)

    if not profile:
        return False

    return profile.role in ["parent_a", "parent_b"]


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
        .filter( user=user)
        .order_by("-is_primary", "-joined_at")
        .first()
    )
    return membership.family if membership else None


def get_family_lawyer(family, lawyer_role="lawyer_a"):
    """
    Restituisce l'utente che ricopre il ruolo di lawyer_a o lawyer_b nella famiglia.
    """
    return (
        family.members
        .select_related("user")
        .filter(role=lawyer_role)
        .first()
    )


def get_family_members_by_role(family, role):
    """
    Restituisce la lista dei membri di una famiglia con un ruolo specifico
    """
    return family.members.filter(role=role)

def get_family_parent(family, role="parent_a"):
    member = family.members.filter(role=role).first()
    return member.user if member else None

def get_user_role_in_family(user, family=None):
    qs = user.family_memberships.select_related("family")

    if family:
        qs = qs.filter(family=family)
    else:
        qs = qs.order_by("-is_primary", "-joined_at")

    membership = qs.first()

    return membership.role if membership else None


# families/utils.py
from accounts.models import UserProfile


def calculate_setup_progress(user):

    profile = UserProfile.objects.filter(user=user).first()

    important_fields = [
        ("address", "Indirizzo"),
        ("phone", "Telefono"),
        ("birth_place", "Luogo di nascita"),
    ]

    completed_labels = []
    missing_labels = []

    completed = 0

    for field_name, label in important_fields:

        value = getattr(profile, field_name, "")

        # ✅ normalizza
        value = str(value).strip() if value is not None else ""

        print(field_name, "=", repr(value))

        if value != "":
            completed += 1
            completed_labels.append(label)
        else:
            missing_labels.append(label)

    total = len(important_fields)

    progress_pct = round((completed / total) * 100) if total else 0

    return (
        progress_pct,
        completed,
        len(missing_labels),
        important_fields,
        completed_labels,
    )