from django.utils import timezone

from families.models import FamilyMember

def accept_invitation(invitation, user):
    # collega utente alla famiglia
    FamilyMember.objects.get_or_create(
        family=invitation.family,
        user=user,
        defaults={
        "role" : invitation.role
    }
    )

    # segna invito come accettato
    invitation.status = "accepted"
    invitation.accepted_at = timezone.now()
    invitation.invited_user = user
    invitation.save()


