import logging
from urllib.parse import unquote

from django.conf import settings
from django.contrib import messages
# accounts/views.py
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from accounts.forms import RegisterForm, UserForm, UserProfileForm
from accounts.models import UserProfile
from accounts.services import email_service
from families.models import Invitation, FamilyMember, Family
from families.services.invitation_service import accept_invitation
from families.utils import get_family_of_user, generate_family_name
from accounts.services.email_service import send_activation_email
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.contrib import messages
from families.models import FamilyMember, Invitation
from families.utils import get_family_of_user
from families.services import invitation_service
from accounts.models import UserProfile
from core.choices import RoleChoices  # ✅ Importa le choices

User = get_user_model()
logger = logging.getLogger(__name__)


def redirect_after_login(request):
    profile = request.user.userprofile
    if profile.role in RoleChoices.lawyer_roles():
        return redirect('families:lawyer_dashboard')
    return redirect('families:family_dashboard')


# =========================
# REGISTRAZIONE
# =========================
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
            profile.role = invitation.role
        profile.save()

        # 3️⃣ Accetta invito → CREA FamilyMember
        if invitation:
            accept_invitation(invitation, user)
            del request.session["invitation_id"]

        # 4️⃣ Email di attivazione
        email_service.send_activation_email(request, user)
        return render(request, "accounts/confirm_email.html")

    return render(request, "accounts/register.html", {"form": form, "invitation": invitation})


# =========================
# ATTIVAZIONE ACCOUNT
# =========================
def activate_account(request):
    # =========================
    # 1. RECUPERO PARAMETRI LINK
    # =========================
    uidb64 = unquote(request.GET.get("uidb64", "")).strip()
    token = unquote(request.GET.get("token", "")).strip()

    if not uidb64 or not token:
        logger.warning("⚠️ Attivazione: parametri mancanti")
        return render(request, "accounts/activation_invalid.html")
    # =========================
    # 2. DECODIFICA USER ID
    # =========================
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
    except (TypeError, ValueError, OverflowError) as e:
        logger.error(f"❌ Errore decodifica UID: {e}")
        try:
            import base64
            # Aggiungi padding se manca
            padded = uidb64 + "=" * (4 - len(uidb64) % 4)
            uid = force_str(base64.urlsafe_b64decode(padded))
        except Exception:
            return render(request, "accounts/activation_invalid.html", {
                "error": "Link di attivazione non valido"
            })
    # =========================
    # 3. TROVA UTENTE
    # =========================
    user = User.objects.filter(pk=uid).first()
    if not user:
        logger.warning(f"⚠️ Utente con pk={uid} non trovato")
        return render(request, "accounts/activation_invalid.html")
    # =========================
    # 4. SE GIA ATTIVO → LOGIN PAGE
    # =========================
    if user.is_active:
        messages.info(request, "Il tuo account è già attivo. Effettua il login.")
        return redirect("accounts:login")
    # =========================
    # 5. VALIDAZIONE TOKEN e  ATTIVA UTENTE
    # =========================
    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        messages.success(request, "✅ Account attivato! Benvenuto.")
        # =========================
        # 7. RECUPERA PROFILO
        # =========================
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else "parent_a"

        # =========================
        # 8. CASO INVITO
        # =========================
        # ✅ FIX: Collega l'utente alla famiglia se c'era un invito in sessione
        invitation_id = request.session.pop("invitation_id", None)
        if invitation_id:
            # ✅ Caso INVITO: accept_invitation crea FamilyMember
            from families.services.invitation_service import accept_invitation
            invitation = Invitation.objects.filter(id=invitation_id, status="pending").first()
            if invitation:
                accept_invitation(invitation, user)  # ← ✅ Crea FamilyMember qui!
                messages.success(request, f"✅ Sei stato aggiunto a {invitation.family.name}")
        # =========================
        # 9. CASO REGISTRAZIONE DIRETTA (NO INVITO)
        # =========================
        else:
            if not FamilyMember.objects.filter(user=user).exists():
                #crea nuova famiglia
                family_name = generate_family_name(user)
                #crea famiglia
                family = Family.objects.create(
                    name=family_name,
                    created_by=user,
                    creator_role=role
                )
                #crea membership
                FamilyMember.objects.create(
                    family=family,
                    user=user,
                    role=role,
                    is_primary=True
                )

                # Marca setup completo
                if profile:
                    profile.setup_complete = True
                    profile.save()

                messages.success(request, f"✅ Famiglia '{family.name}' creata!")
            # =========================
            # 10. REDIRECT INTELLIGENTE
            # =========================
            # ✅ Redirect intelligente: dashboard se ha famiglia, setup solo se manca

        if profile and profile.role.startswith("lawyer"):
            return redirect("lawyer_dashboard")

        # Se ha una famiglia (dovrebbe averla ora), vai a dashboard
        from families.utils import get_family_of_user
        if get_family_of_user(user):
            return redirect("families:family_dashboard")

        # Fallback raro: se per qualche motivo manca, vai a setup
        return redirect("families:setup")

    logger.warning(f"⚠️ Token non valido per utente {user.pk}")

    return render(request, "accounts/activation_invalid.html", {
        "error": "Link di attivazione non valido o scaduto."
    })


# =========================
# LOGIN
# =========================
# accounts/views.py


# accounts/views.py
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from families.utils import get_family_of_user
from core.choices import RoleChoices


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # 🔥 Gestione invito (tieni il tuo codice se presente)
            # 🔑 GESTIONE INVITO PENDENTE (per avvocati con più famiglie)
            pending_token = request.session.pop("pending_invite_token", None)
            if pending_token:
                from families.services.invitation_service import accept_invitation
                from families.models import Invitation
                from django.contrib import messages

                try:
                    invitation = Invitation.objects.select_related('family').get(
                        token=pending_token,
                        status="pending"
                    )
                    # ✅ Aggiungi l'utente alla famiglia (crea FamilyMember)
                    accept_invitation(invitation, user)
                    messages.success(request, f"✅ Sei stato aggiunto a '{invitation.family.name}'")
                except Invitation.DoesNotExist:
                    messages.warning(request, "⚠️ Invito non valido o già utilizzato")
                except Exception as e:
                    # Logga l'errore per debugging, ma non esporlo all'utente
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Errore accettazione invito {pending_token}: {e}")
                    messages.error(request, "⚠️ Si è verificato un errore tecnico. Contatta il supporto.")

            profile = getattr(user, 'profile', None)
            if not profile:
                return redirect('families:setup')

            # 🎯 1. AVVOCATI
            if profile.role in RoleChoices.lawyer_roles():
                if profile.setup_complete:
                    return redirect('families:lawyer_dashboard')
                return redirect('families:summary')

            # 🎯 2. GENITORI
            family = get_family_of_user(user)
            if not family:
                return redirect('families:setup')

            if not profile.setup_complete:
                return redirect('families:summary')

            # ✅ Tutto ok
            return redirect('families:family_dashboard')

        # ⚠️ Se il form NON è valido, il codice CONTINUA qui sotto
        # e restituisce il form con gli errori evidenziati

    else:
        form = AuthenticationForm()

    # 🔴 CRUCIALE: Questo return DEVE essere allo stesso livello di "if request.method"
    # Se è indentato dentro l'if, Django restituisce None nei casi non gestiti.
    return render(request, "accounts/login.html", {"form": form})


# =========================
# IMPOSTAZIONI PROFILO (CON PROTEZIONE CAMPI BLOCCATI)
# =========================
@login_required
def profile_settings_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        user_form = UserForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, instance=profile, role=profile.role)

        if user_form.is_valid() and profile_form.is_valid():
            # 🔐 PROTEZIONE ANTI-MANOMISSIONE: rimuovi campi bloccati dai dati validati
            user_data = user_form.cleaned_data.copy()
            profile_data = profile_form.cleaned_data.copy()

            # Se il profilo esiste già → ignora tentativi di modifica dei campi bloccati
            if user.pk:
                for field in ["first_name", "last_name", "email"]:
                    user_data.pop(field, None)
            if profile.pk and 'phone' in profile_data:
                profile_data.pop('phone', None)

            # Salva SOLO i campi rimanenti
            with transaction.atomic():
                if user_data:
                    User.objects.filter(pk=user.pk).update(**user_data)
                if profile_data:
                    UserProfile.objects.filter(pk=profile.pk).update(**profile_data)

            messages.success(request, "✅ Profilo aggiornato")
            return redirect("accounts:settings")
    else:
        user_form = UserForm(instance=user)
        profile_form = UserProfileForm(instance=profile, role=profile.role)

    return render(request, "accounts/settings.html", {
        "form_user": user_form,
        "form_profile": profile_form,
    })


# =========================
# RESEND ACTIVATION
# =========================
def resend_activation(request):
    """View per richiedere un nuovo link di attivazione."""

    if request.method != "POST":
        return render(request, "accounts/resend_activation.html")

    email = request.POST.get("email", "").strip().lower()

    # Cerca utente inattivo
    user = User.objects.filter(email=email, is_active=False).first()

    if user and send_activation_email(request, user, subject_prefix="Nuovo "):
        messages.success(request, "✅ Nuova email di attivazione inviata!")
    else:
        # ⚠️ Security: non rivelare se l'utente esiste o meno
        messages.success(
            request,
            "✅ Se l'email esiste ed è inattiva, riceverai un nuovo link di attivazione."
        )
        if not user:
            logger.warning(f"⚠️ Tentativo resend per email non trovata/inattiva: {email}")

    return redirect("accounts:login")


# =========================
# LOGOUT
# =========================
def logout_view(request):
    logout(request)
    return redirect("/")
