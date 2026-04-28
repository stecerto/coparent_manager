from .models import FamilyMember


def family_membership(request):
    if not request.user.is_authenticated:
        return {}

    membership = (
        FamilyMember.objects
        .select_related("family")
        .filter(user=request.user)
        .first()
    )

    return {
        "membership": membership
    }