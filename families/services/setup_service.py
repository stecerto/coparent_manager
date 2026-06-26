

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.forms import FirstLoginForm, UserProfileForm
from accounts.models import UserProfile
from children.models import ChildProfile
from families.models import FamilyMember, Family
from families.utils import get_family_of_user


@login_required
def handle_setup(request, mode="setup"):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # ✅ AVVOCATI/MEDIATORI/CONSULENTI: Non devono fare setup famiglia
    if profile.role in ["lawyer", "mediator", "consultant"]:
        messages.info(request, "✅ Il tuo profilo professionale è attivo. Riceverai inviti dalle famiglie.")
        return redirect('families:professional_dashboard')

    # ✅ GENITORI: Procedi con il setup famiglia
    family = get_family_of_user(user)

    child_formset = build_child_formset(
        family=family,
        post_data=request.POST if request.method == "POST" else None
    )

    if request.method == "POST":
        if child_formset.is_valid():
            # ✅ CREA FAMIGLIA SOLO PER GENITORI SENZA FAMIGLIA
            if not family:
                existing_membership = FamilyMember.objects.filter(user=user).first()
                if existing_membership:
                    family = existing_membership.family
                else:
                    # 🆕 Crea famiglia SOLO per genitori
                    family = Family.objects.create(
                        name=f"Famiglia {user.last_name or 'Nuova'}",
                        created_by=user,
                        creator_role="parent_a"
                    )
                    FamilyMember.objects.create(
                        family=family,
                        user=user,
                        role="parent_a",
                        is_primary=True
                    )

            save_children(child_formset, family, user)
            complete_setup(profile)
            messages.success(request, f"✅ Setup completato! Benvenuto nella tua famiglia.")
            return redirect("families:family_dashboard")

    # ✅ CORRETTO: Usa render() invece di restituire un dizionario
    return render(request, "families/setup.html", {
        "form_user": FirstLoginForm(instance=user),
        "form_profile": UserProfileForm(instance=profile),
        "formset": child_formset,
        "is_setup": True,
        "family": family
    })



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