import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from families.services.invitation_service import accept_invitation
from families.models import FamilyMember
from families.services.memberships import add_user_to_family
from families.utils import get_family_of_user
from .forms import RegisterForm, UserForm, UserProfileForm
from .services import email_service

User = get_user_model()


def redirect_after_login(request):
    profile = request.user.userprofile

    if profile.role == 'lawyer':
        return redirect('lawyer_dashboard')

    return redirect('families:family_dashboard')


# =========================
# REGISTRAZIONE
# =========================
from families.models import Invitation
from accounts.models import UserProfile
from django.utils import timezone


# accounts/views.py
from families.services.invitation_service import accept_invitation
from accounts.services import email_service

def register_view(request):
    invitation = None
    invitation_id = request.session.get("invitation_id")

    if invitation_id:
        invitation = Invitation.objects.filter(id=invitation_id, status="pending").first()

    initial_data = {}
    if invitation and request.method == "GET":
        initial_data["email"] = invitation.email

    form = RegisterForm(request.POST or None, initial=initial_data)

    if request.method == "POST" and form.is_valid():
        # 1️⃣ Crea utente (inattivo fino ad attivazione)
        user = form.save(commit=False)
        user.is_active = False
        user.save()

        # 2️⃣ Crea profilo
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if invitation:
            profile.role = invitation.role  # Fallback, verrà sincronizzato da accept_invitation
        profile.save()

        # 3️⃣ ✅ Accetta invito → CREA FamilyMember nella famiglia corretta
        if invitation:
            accept_invitation(invitation, user)
            del request.session["invitation_id"]  # Pulisci sessione

        # 4️⃣ Email di attivazione
        email_service.send_activation_email(request, user)
        return render(request, "accounts/confirm_email.html")

    return render(request, "accounts/register.html", {"form": form, "invitation": invitation})

# =========================
# ATTIVAZIONE ACCOUNT
# =========================
logger = logging.getLogger(__name__)
User = get_user_model()


def activate_account(request):
    uidb64 = request.GET.get("uidb64")
    token = request.GET.get("token")

    # 1️⃣ Validazione input
    if not uidb64 or not token:
        logger.warning("⚠️ Attivazione: parametri mancanti")
        return render(request, "accounts/activation_invalid.html")

    # 2️⃣ Decodifica UID con logging
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        logger.info(f"🔍 UID decodificato: {uid}")
    except (TypeError, ValueError, OverflowError) as e:
        logger.error(f"❌ Errore decodifica UID: {e}")
        return render(request, "accounts/activation_invalid.html")

    # 3️⃣ Cerca utente
    user = User.objects.filter(pk=uid).first()
    if not user:
        logger.warning(f"⚠️ Utente con pk={uid} non trovato")
        return render(request, "accounts/activation_invalid.html")

    # 4️⃣ Già attivo? → redirect gentile
    if user.is_active:
        logger.info(f"✅ Utente {user.email} già attivo")
        messages.info(request, "Il tuo account è già attivo. Effettua il login.")
        return redirect("accounts:login")

    # 5️⃣ Debug token (SOLO in sviluppo)
    if settings.DEBUG:
        logger.info(f"🔐 Token check per {user.email}:")
        logger.info(f"   - Token ricevuto: {token[:20]}...")
        logger.info(f"   - Password hash: {user.password[:20]}...")
        logger.info(f"   - Last login: {user.last_login}")
        logger.info(f"   - Date joined: {user.date_joined}")

    # 6️⃣ Verifica token
    token_valid = default_token_generator.check_token(user, token)
    logger.info(f"🔑 Token valido: {token_valid}")

    if token_valid:
        user.is_active = True
        user.save()
        logger.info(f"🎉 Utente {user.email} attivato con successo!")

        # Login automatico (opzionale)
        login(request, user)
        messages.success(request, "✅ Account attivato! Benvenuto.")

        # Redirect intelligente
        profile = getattr(user, 'userprofile', None)
        if profile and profile.role == 'lawyer':
            return redirect("families:setup")  # o lawyer_dashboard
        return redirect("families:setup")  # o family_dashboard
    else:
        # 🚨 FALLIMENTO: mostra pagina con opzioni di recupero
        logger.warning(f"❌ Token non valido per {user.email}")
        return render(request, "accounts/activation_invalid.html", {
            "user_email": user.email,  # Per mostrare "Rinvia email a xxx"
            "can_resend": True
        })


# =========================
# LOGIN
# =========================
def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # 🔥 GESTIONE INVITO PENDENTE
            pending_token = request.session.pop("pending_invite_token", None)

            if pending_token:
                invitation = Invitation.objects.filter(
                    token=pending_token,
                    status="pending"
                ).first()

                if invitation and not invitation.is_expired:
                    add_user_to_family(user, invitation)
                    invitation.mark_accepted(user)
                    invitation.status = "accepted"
                    invitation.accepted_at = timezone.now()
                    invitation.invited_user = user
                    invitation.save()

                    return redirect("families:summary")
            profile = UserProfile.objects.filter(user=user).first()
            family = get_family_of_user(user)
            # 🔴 1. se NON ha famiglia → setup
            if not family:
                return redirect('families:setup')

            # 🟡 2. se profilo incompleto
            if not profile or not profile.setup_complete:
                return redirect('families:setup')

            # 🟢 3. ruolo nella famiglia
            membership = FamilyMember.objects.filter(user=user).first()

            if membership:
                if membership.role.startswith("lawyer"):
                    return redirect("families:setup")
                else:
                    return redirect("families:setup")

            # fallback
            return redirect("families:summary")
    else:
        form = AuthenticationForm()
    return render(request, "accounts/login.html", {"form": form})

@login_required
def profile_settings_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        user_form = UserForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()

            return redirect("accounts:settings")

    else:
        user_form = UserForm(instance=user)
        profile_form = UserProfileForm(instance=profile)

    return render(request, "accounts/settings.html", {
        "form_user": user_form,
        "form_profile": profile_form,
    })


 # o senza login se vuoi permettere a chiunque
def resend_activation(request):
    if request.method == "POST":
        email = request.POST.get("email")
        user = User.objects.filter(email=email, is_active=False).first()

        if user:
            # Rigenera token
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            # Invia nuova email
            activation_link = request.build_absolute_uri(
                f"/accounts/activate/?uidb64={uidb64}&token={token}"
            )

            html_message = render_to_string("emails/activation_email.html", {
                "user": user,
                "activation_link": activation_link,
            })

            send_mail(
                subject="Nuovo link di attivazione",
                message="Clicca sul link per attivare il tuo account",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message
            )
            messages.success(request, "✅ Nuova email di attivazione inviata!")
        else:
            messages.error(request, "❌ Utente non trovato o già attivo.")

        return redirect("accounts:login")

    return render(request, "accounts/resend_activation.html")


# =========================
# LOGOUT
# =========================
def logout_view(request):
    logout(request)
    return redirect("/")
