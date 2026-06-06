# families/signal_handlers.py
import logging
from django.dispatch import receiver
from families.signals import user_activated
from families.models import Invitation, Family, FamilyMember
from families.services.invitation_service import accept_invitation
from families.utils import generate_family_name

logger = logging.getLogger(__name__)


@receiver(user_activated)
def process_pending_invitations(sender, user, **kwargs):
    """
    Quando un utente viene attivato, controlla se ha inviti pendenti.
    Se sì, li accetta automaticamente.
    """
    logger.info(f"🎯 Handler segnale: elaborazione inviti per {user.email}")

    # Cerca inviti pendenti per questa email
    pending_invitations = Invitation.objects.filter(
        email=user.email,
        status="pending"
    )

    if not pending_invitations.exists():
        logger.info(f"ℹ️ Nessun invito pendente per {user.email}")
        return

    for invitation in pending_invitations:
        try:
            logger.info(f"✅ Accetto invito {invitation.id} per {user.email}")
            accept_invitation(invitation, user)
            logger.info(f"✅ Invito {invitation.id} accettato con successo")
        except Exception as e:
            logger.error(f"❌ Errore nell'accettazione dell'invito {invitation.id}: {e}")


@receiver(user_activated)
def create_family_for_parent(sender, user, **kwargs):
    """
    Quando un genitore viene attivato e non ha inviti pendenti,
    crea automaticamente una famiglia per lui.
    """
    logger.info(f"🏠 Handler segnale: verifica creazione famiglia per {user.email}")

    # Controlla se l'utente è un genitore (non professionista)
    profile = getattr(user, 'userprofile', None)
    if not profile:
        return

    # Se è un professionista, non creare famiglia automatica
    if profile.role in ['lawyer', 'mediator', 'consultant']:
        logger.info(f"ℹ️ Utente {user.email} è professionista, skip creazione famiglia")
        return

    # Controlla se ha già una famiglia
    if FamilyMember.objects.filter(user=user).exists():
        logger.info(f"ℹ️ Utente {user.email} ha già una famiglia, skip")
        return

    # Controlla se aveva un invito pendente (se sì, è già stato gestito dall'altro handler)
    if Invitation.objects.filter(email=user.email, status__in=['pending', 'accepted']).exists():
        logger.info(f"ℹ️ Utente {user.email} aveva un invito, skip creazione automatica")
        return

    # Crea la famiglia
    try:
        family_name = generate_family_name(user)
        family = Family.objects.create(
            name=family_name,
            created_by=user,
            creator_role="parent_a"
        )
        FamilyMember.objects.create(
            family=family,
            user=user,
            role="parent_a",
            is_primary=True
        )
        logger.info(f"✅ Famiglia '{family_name}' creata per {user.email}")
    except Exception as e:
        logger.error(f"❌ Errore nella creazione della famiglia per {user.email}: {e}")