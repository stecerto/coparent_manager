import secrets
import uuid

from django.contrib.admin import display
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.shortcuts import render, redirect

from django.utils import timezone
from django.views import defaults


from families.models import FamilyMember
from families.models import Invitation
from families.services.email_service import send_invitation_email

BASE_URL = "http://127.0.0.1:8000" #"https://yourdomain.com"
#domain = request.get_host()
def create_invitation(
    family,
    role,
    channel,
    email=None,
    phone=None,
    sender=None,
    token=None,
    expire_at=None,
    display_name=None
):
    existing = Invitation.objects.filter(
        family=family,
        role=role,
        email=email,
        phone=phone,
        status="pending"
    ).exclude(status="accepted").first()

    if existing:
        raise ValidationError(
            "Esiste già un invito pendente per questo contatto."
        )


    if token is None:
        token = uuid.uuid4()

    invitation = Invitation.objects.create(
        family=family,
        role=role,
        channel=channel,
        email=email if channel == "email" else None,
        phone=phone if channel == "whatsapp" else None,
        invited_by=sender,
        token=token,
        expire_at=expire_at,
        status="pending",
        display_name=display_name

    )

    return invitation



def generate_token():
    return secrets.token_urlsafe(32)


def build_invite_link(invitation):
    return f"{BASE_URL}/invite/{invitation.token}"


def build_whatsapp_link(request,invitation):
    from urllib.parse import quote

    link = request.build_absolute_uri(
        f"/families/invite/{invitation.token}/"
    )
    message = (f"Sei stato invitato su CoParentManager.\n"
               f"Apri il link: {link}")

    return f"https://wa.me/?text={quote(message)}"





def accept_invitation(invitation, user):
    if invitation.is_expired:
        invitation.mark_expired()
        return None

    if invitation.status != "pending":
        return invitation

    FamilyMember.objects.get_or_create(
        family=invitation.family,
        user=user,
        defaults={"role": invitation.role}
    )

    invitation.mark_accepted(user)

    profile = user.userprofile
    profile.role = invitation.role
    profile.save()

    return invitation

def store_invitation_in_session(request, invitation):
    request.session["invitation_id"] = invitation.id


def get_session_invitation(request):
    invitation_id = request.session.get("invitation_id")

    if not invitation_id:
        return None

    return Invitation.objects.filter(
        id=invitation_id,
        accepted=False
    ).first()


# =========================
# REGISTRAZIONE
# =========================


def register_member_view(request,user):
    invitation_id = request.session.get('invitation_id')
    # Gestione invito
    if invitation_id:
        try:
            invitation = Invitation.objects.get(id=invitation_id, accepted=False)
            accept_invitation(invitation, user)

            profile = user.userprofile
            profile.role = invitation.role
            profile.save()
        except Invitation.DoesNotExist:
            pass

def build_invitation_context(invitation, request_user, profile=None):
    role = invitation.role

    inviter_name = (
        f"{request_user.first_name} {request_user.last_name}"
        or request_user.username
    )

    subject_name = None

    if role == "parent_b":
        title = "Invito alla famiglia"
        message = "Sei stato invitato come secondo genitore."

        if profile:
            subject_name = (
                f"{profile.parent_a_name} {profile.parent_a_surname}"
            )

    elif role == "lawyer_a":
        title = "Invito come avvocato"
        message = "Sei stato indicato come avvocato del genitore A."

        if profile:
            subject_name = (
                f"{profile.parent_a_name} {profile.parent_a_surname}"
            )

    elif role == "lawyer_b":
        title = "Invito come avvocato"
        message = "Sei stato indicato come avvocato del genitore B."

        if profile:
            subject_name = (
                f"{profile.parent_b_name} {profile.parent_b_surname}"
            )

    else:
        title = "Invito alla piattaforma"
        message = "Sei stato invitato a partecipare."

    return {
        "invitation_title": title,
        "invitation_message": message,
        "subject_name": subject_name,
        "inviter_name": inviter_name,
    }

def add_member(family, user, role):
    return FamilyMember.objects.get_or_create(
        family=family,
        user=user,
        role=role
    )




def map_invitation_role(inv_role):
    """
    Mappa ruolo invito → ruolo FamilyMember
    """
    mapping = {
        "parent_b": "parent_b",
        "lawyer": "lawyer_a",  # oppure logica più avanzata
    }
    return mapping.get(inv_role, "parent_b")