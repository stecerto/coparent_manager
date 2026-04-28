from django.contrib.auth.models import AbstractUser
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from config import settings


from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_invitation_email(
    request,
    invitation,
    template="emails/invitation_email.html",
    context_extra=None
):
    invite_link = request.build_absolute_uri(
        reverse("families:accept_invite", kwargs={"token": str(invitation.token)})
    )

    context = {
        "invite_link": invite_link,
        "email": invitation.email,
        "role": invitation.role,
        "invitation": invitation,
    }

    if context_extra:
        context.update(context_extra)

    subject = build_subject(invitation)

    html_message = render_to_string(template, context)

    send_mail(
        subject=subject,
        message=f"Apri questo link: {invite_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        html_message=html_message,
        fail_silently=False
    )

def build_subject(invitation):
    role_subjects = {
         "parent_b": "Invito come genitore alla gestione familiare",
        "lawyer_a": f"Invito come avvocato della famiglia {invitation.display_name or invitation.email} (genitore A)",
        "lawyer_b": f"Invito come avvocato della famiglia {invitation.display_name or invitation.email} (genitore B)",
    }

    return role_subjects.get(
        invitation.role,
        "Invito alla piattaforma familiare"
    )


def build_invitation_context(request, invitation, family=None):
    inviter_name = (f"{request.user.first_name} {request.user.last_name}".strip()
    or request.user.email)

    role = invitation.role
    subject_name = invitation.display_name or invitation.email

    if role == "parent_b":
        title = "Invito all' App gestione famiglia"
        message = "Sei stato invitato come secondo genitore."
        subject_name = invitation.display_name or invitation.email
           # f"{profile.parent_a_name} {profile.parent_a_surname}"
         #   if family else None


    elif role == "lawyer_a":
        title = "Invito come avvocato"
        message = "Sei stato indicato come avvocato del genitore A."
        subject_name = (
            f"{request.user.first_name} {request.user.last_name}"
            if family else None
        )

    elif role == "lawyer_b":
        title = "Invito come avvocato"
        message = "Sei stato indicato come avvocato del genitore B."
        subject_name = (
            f"{request.user.first_name} {request.user.last_name}"
            if family else None
        )

    else:
        title = "Invito alla piattaforma"
        message = "Sei stato invitato."

    return {
        "invitation_title": title,
        "invitation_message": message,
        "subject_name": subject_name,
        "inviter_name": inviter_name,
    }