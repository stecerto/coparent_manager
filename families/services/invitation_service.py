import secrets
import uuid
from urllib import request

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from psycopg.types import none

from families.models import FamilyMember
from families.models import Invitation
from families.utils import get_user_role_in_family, can_lawyer_add_family

User = get_user_model()

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
    # =========================
    # 1. VALIDAZIONE SENDER
    # =========================
    if sender is None:
        raise ValueError("sender (request.user) è obbligatorio")

    inviter_profile = getattr(sender, "userprofile", None)
    inviter_role = inviter_profile.role if inviter_profile else None

    # =========================
    # 2. MAP RUOLO
    # =========================
    invited_role = map_invitation_role(role, inviter_role)

    # =========================
    # 3. CONTROLLO INVITI DUPLICATI
    # =========================
    existing = Invitation.objects.filter(
        family=family,
        role=invited_role,
        email=email,
        phone=phone,
        status="pending"
    ).first()

    if existing:
        raise ValidationError(
            "Esiste già un invito pendente per questo contatto."
        )

    # =========================
    # 4. TOKEN
    # =========================
    if token is None:
        token = uuid.uuid4()

    # =========================
    # 5. CREA INVITO
    # =========================
    invitation = Invitation.objects.create(
        family=family,
        role=invited_role,
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


# families/services/invitation_service.py
@transaction.atomic
def accept_invitation(invitation, user):
    """
    Accetta un invito e sincronizza FamilyMember + UserProfile.
    ✅ Se l'invito non ha una famiglia (invito da avvocato a nuovo genitore), la crea automaticamente.
    """
    role = invitation.role
    role_base = role.replace('_a', '').replace('_b', '')
    if role_base in ['mediator', 'consultant']:
        role = role_base  # Usa solo 'mediator' o 'consultant'

    # 🛡️ 0. Controllo email
    if invitation.email and user.email.lower() != invitation.email.lower():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(
            f"⚠️ Questo invito è destinato a {invitation.email}, non a {user.email}. "
            f"Registrati con l'email corretta o contatta chi ti ha invitato."
        )

    # 🛡️ 1. Controlli preliminari
    if invitation.is_expired:
        invitation.mark_expired()
        return None

    if invitation.status != "pending":
        return invitation

    # ✅ CONTROLLO LIMITE SE L'UTENTE È UN AVVOCATO
    if invitation.role in ["lawyer_a", "lawyer_b"] and hasattr(user, 'profile'):
        can_add, limit, current = can_lawyer_add_family(user)
        if not can_add:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(
                f"Hai raggiunto il limite di {limit} famiglie per il piano {user.profile.plan}. "
                f"Contatta l'amministratore per upgrade."
            )

    # 🌟 2. SE NON C'È UNA FAMIGLIA, LA CREAMO ORA!
    if not invitation.family:
        from families.utils import generate_family_name
        from families.models import Family

        # Crea la famiglia con il nome del genitore che accetta
        family_name = generate_family_name(user)
        new_family = Family.objects.create(
            name=family_name,
            created_by=user,
            creator_role="parent_a"
        )

        # Aggiorna l'invito con la nuova famiglia
        invitation.family = new_family
        invitation.save()

        # Assegna il ruolo parent_a all'utente che sta accettando
        FamilyMember.objects.create(
            family=new_family,
            user=user,
            role="parent_a",
            is_primary=True
        )

        # Assegna il ruolo all'avvocato che ha inviato l'invito
        if invitation.invited_by:
            FamilyMember.objects.create(
                family=new_family,
                user=invitation.invited_by,
                role="lawyer_a",
                is_primary=False
            )

    # ✅ 3. Crea o aggiorna FamilyMember (logica esistente)
    member, created = FamilyMember.objects.get_or_create(
        family=invitation.family,
        user=user,
        defaults={"role": invitation.role}
    )

    # ✅ 4. Aggiorna ruolo se cambiato
    if not created and member.role != invitation.role:
        member.role = invitation.role
        member.save()

    # ⚠️ NON sovrascrivere userprofile.role se già impostato
    profile = getattr(user, 'userprofile', None)
    if profile and not profile.role:
        generic_role = invitation.role.replace('_a', '').replace('_b', '')
        profile.role = generic_role
        profile.save()

    # ✅ 5. Marca invito come accettato
    invitation.mark_accepted(user)

    return invitation

def store_invitation_in_session(request, invitation):
    request.session["invitation_id"] = invitation.id


def get_session_invitation(request):
    invitation_id = request.session.get("invitation_id")

    if not invitation_id:
        return None

    return Invitation.objects.filter(
        id=invitation_id,
        status="pending"
    ).first()


# =========================
# REGISTRAZIONE
# =========================

'''
def register_member_view(request,user):
    invitation_id = request.session.get('invitation_id')
    # Gestione invito
    if invitation_id:
        try:
            invitation = Invitation.objects.get(id=invitation_id, accepted=False)
            accept_invitation(invitation, user)

            if profile and not profile.role:  # ← Solo se vuoto!
                profile.role = invitation.role
                profile.save()
        except Invitation.DoesNotExist:
            pass
'''
def build_invitation_context(invitation, request_user = None, profile=None):
    role = invitation.role

    inviter_name = (
        f"{request_user.first_name} {request_user.last_name}"
        or request_user.username
    )

    subject_name = None

    if role == "parent_b":
        title = "Invito alla famiglia"
        message = "Sei stato invitato come secondo genitore."

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




def map_invitation_role(invitation_role, inviter_role=None):
    """
    Determina il ruolo finale nel sistema FamilyMember
    """

    if invitation_role == "parent_b":
        return "parent_b"

    if invitation_role == "lawyer":
        # 🔥 dipende da chi invita
        if inviter_role == "parent_a":
            return "lawyer_a"
        if inviter_role == "parent_b":
            return "lawyer_b"

    return invitation_role