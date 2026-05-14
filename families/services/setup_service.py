

from django import forms
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory
from django.shortcuts import redirect, render
from django.utils import timezone

from children.models import ChildProfile
from families.models import FamilyMember, Family
from families.utils import get_family_of_user
from accounts.models import UserProfile
from accounts.forms import FirstLoginForm, UserProfileForm
from families.services.email_service import send_invitation_email


@login_required
def handle_setup(request, mode="setup"):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # 🔍 Cerca famiglia esistente (da invito o già creata)
    family = get_family_of_user(user)

    child_formset = build_child_formset(
        family=family,
        post_data=request.POST if request.method == "POST" else None
    )

    if request.method == "POST":
        if child_formset.is_valid():

            # ✅ LOGICA DI SICUREZZA: Non creare nuova famiglia se l'utente è già membro
            if not family:
                # Fallback: cerca membership esistente ma non linkata correttamente
                existing_membership = FamilyMember.objects.filter(user=user).first()
                if existing_membership:
                    family = existing_membership.family
                else:
                    # 🆕 Crea famiglia SOLO per registrazioni DIRETTE (senza invito)
                    creator_role = "lawyer_a" if profile.role.startswith("lawyer") else "parent_a"
                    family = Family.objects.create(
                        name=f"Famiglia {user.last_name or 'Nuova'}",
                        created_by=user,
                        creator_role=creator_role
                    )
                    FamilyMember.objects.create(
                        family=family,
                        user=user,
                        role=creator_role,
                        is_primary=True
                    )

            # 🔄 Sincronizza ruolo profilo con quello effettivo del membership
            member = FamilyMember.objects.filter(family=family, user=user).first()
            if member and profile.role != member.role:
                profile.role = member.role
                profile.save()

            save_children(child_formset, family, user)
            complete_setup(profile)

            return redirect("families:family_dashboard")  # o summary, in base al tuo routing

    return {
        "context": {
            "form_user": FirstLoginForm(instance=user),
            "form_profile": UserProfileForm(instance=profile),
            "formset": child_formset,
            "is_setup": True,
            "family": family  # Utile per il template
        }
    }



# =========================
# FUNZIONI HELPER
# =========================

def invalid_response(form_user, form_profile, formset):
    return {
        "redirect": None,
        "context": {
            "form_user": form_user,
            "form_profile": form_profile,
            "formset": formset
        }
    }


def build_child_formset(family=None, post_data=None):
    ChildFormSet = modelformset_factory(
        ChildProfile,
        fields=["name", "surname", "birth_date", "notes"],
        extra=0,
        can_delete = True,
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"})
        }
    )

    queryset = ChildProfile.objects.none()

    if family:
        queryset = ChildProfile.objects.filter(
            family=family,
            is_active=True
        )

    return ChildFormSet(
        post_data,
        queryset=queryset,
        prefix="children"
    )

def save_children(formset, family, user):

    if not formset.is_valid():
        return

    instances = formset.save(commit=False)

    for child in instances:
        child.family = family  # 🔥 OBBLIGATORIO
        child.modified_by = user
        child.save()

    # 🔥 DELETE CORRETTO
    for obj in formset.deleted_objects:
        obj.archived_at = timezone.now()
        obj.archived_by = user
        obj.is_active = False
        obj.save()


def complete_setup(profile):
    profile.setup_complete = True
    profile.save()