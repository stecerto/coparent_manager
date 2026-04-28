from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from families.models import FamilyMember, Invitation
from families.utils import get_family_of_user
from families.services import invitation_service
from families.services.memberships import add_user_to_family

from .forms import RegisterForm, UserForm, UserProfileForm
from .models import UserProfile
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


def register_view(request):
    invitation = None
    invitation_id = request.session.get("invitation_id")

    if invitation_id:
        invitation = Invitation.objects.filter(
            id=invitation_id,
            status="pending"
        ).first()

    # ✅ PRECOMPILA EMAIL
    initial_data = {}
    if invitation and request.method == "GET":
        initial_data["email"] = invitation.email

    form = RegisterForm(
        request.POST or None,
        initial=initial_data
    )

    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.is_active = False
        user.save()

        # ✅ CREA / AGGIORNA PROFILO CON RUOLO INVITO
        if invitation:
            profile, _ = UserProfile.objects.get_or_create(
                user=user
            )

            profile.role = invitation.role
            profile.save()

            invitation.status = "accepted"
            invitation.invited_user = user
            invitation.accepted_at = timezone.now()
            invitation.save()

            del request.session["invitation_id"]

        email_service.send_activation_email(request, user)

        return render(
            request,
            "accounts/confirm_email.html"
        )

    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            "invitation": invitation
        }
    )
# =========================
# ATTIVAZIONE ACCOUNT
# =========================
def activate_account(request):
    uidb64 = request.GET.get("uidb64")
    token = request.GET.get("token")

    # DEBUG (aggiungi questo)
    # print("RAW UID:", uidb64)
    # print("RAW TOKEN:", token)

    if not uidb64 or not token:
        return render(request, "accounts/activation_invalid.html")
    # uidb64 = uidb64.replace(" ", "").replace("\n", "")
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
    except Exception as e:
        # print("UID ERROR:", e)
        return render(request, "accounts/activation_invalid.html")

    user = User.objects.filter(pk=uid).first()

    # 🚨 BLOCCO RIUSO LINK
    if not user:
        return render(request, "accounts/activation_invalid.html")
    if user.is_active:
        return render(request, "accounts/already_activated.html")

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        return redirect("login")

    return render(request, "accounts/activation_invalid.html")


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




# =========================
# LOGOUT
# =========================
def logout_view(request):
    logout(request)
    return redirect("/")
