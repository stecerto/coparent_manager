from families.models import FamilyMember


def add_user_to_family(user, invitation):
    membership, created = FamilyMember.objects.get_or_create(
        user=user,
        family=invitation.family,
        defaults={
            "role": invitation.role,
        }
    )
    return membership