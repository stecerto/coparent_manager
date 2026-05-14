# families/services/email_service.py
from django.conf import settings  # ✅ Solo questo, non "from config import settings"
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse


def send_invitation_email(
    request,
    invitation,
    template="emails/invitation_email.html",
    context_extra=None
):
    """
    Invia email di invito con link di accettazione.
    """
    # Costruisci link di accettazione
    invite_link = request.build_absolute_uri(
        reverse("families:accept_invite", kwargs={"token": str(invitation.token)})
    )

    # Contesto base per il template email
    context = {
        "invite_link": invite_link,
        "email": invitation.email,
        "role": invitation.role,
        "invitation": invitation,
        "family_name": invitation.family.name if invitation.family else "",
    }

    if context_extra:
        context.update(context_extra)

    subject = build_subject(invitation)
    html_message = render_to_string(template, context)

    send_mail(
        subject=subject,
        message=f"Apri questo link per accettare l'invito: {invite_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        html_message=html_message,
        fail_silently=False
    )


def build_subject(invitation):
    """
    Costruisce l'oggetto dell'email in base al ruolo invitato.
    """
    role_subjects = {
        "parent_b": "👨‍👩‍👧‍👦 Invito alla gestione familiare - CoParentManager",
        "lawyer_a": f"⚖️ Invito come avvocato (Genitore A) - CoParentManager",
        "lawyer_b": f"⚖️ Invito come avvocato (Genitore B) - CoParentManager",
        "mediator": "🤝 Invito come mediatore - CoParentManager",
        "consultant": "💼 Invito come consulente - CoParentManager",
    }
    return role_subjects.get(
        invitation.role,
        "🔗 Invito alla piattaforma - CoParentManager"
    )


def build_invitation_context(request, invitation, family=None):
    """
    Costruisce il contesto per il template email di invito.
    """
    inviter_name = (
        f"{request.user.first_name} {request.user.last_name}".strip()
        or request.user.email
        or "Un membro della famiglia"
    )

    role = invitation.role
    subject_name = invitation.display_name or invitation.email or "il tuo ruolo"

    # Mappa titoli e messaggi per ruolo
    role_config = {
        "parent_b": {
            "title": "👨‍👩‍👧‍👦 Invito alla gestione familiare",
            "message": "Sei stato invitato come secondo genitore per gestire spese, calendario e documenti della famiglia.",
        },
        "lawyer_a": {
            "title": "⚖️ Invito come avvocato (Genitore A)",
            "message": "Sei stato indicato come legale di riferimento per il genitore A.",
        },
        "lawyer_b": {
            "title": "⚖️ Invito come avvocato (Genitore B)",
            "message": "Sei stato indicato come legale di riferimento per il genitore B.",
        },
        "mediator": {
            "title": "🤝 Invito come mediatore familiare",
            "message": "Sei stato invitato come mediatore per supportare la famiglia.",
        },
        "consultant": {
            "title": "💼 Invito come consulente",
            "message": "Sei stato invitato come consulente per supportare la famiglia.",
        },
    }

    config = role_config.get(role, {
        "title": "🔗 Invito alla piattaforma",
        "message": "Sei stato invitato a partecipare alla piattaforma CoParentManager.",
    })

    return {
        "invitation_title": config["title"],
        "invitation_message": config["message"],
        "subject_name": subject_name,
        "inviter_name": inviter_name,
        "role_label": dict(invitation.ROLE_CHOICES).get(role, role),
    }