from families.models import Family


def get_user_from_lawyer(lawyer):
    return getattr(lawyer, "user", None) if lawyer else None



def create_or_get_family(user, profile):
    family, created = Family.objects.get_or_create(
        created_by=user,
        defaults={"name": f"Famiglia di {user.email}"}
    )
    return family


