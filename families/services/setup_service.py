

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
def handle_setup(request,  mode="setup"):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    family = get_family_of_user(user)

    child_formset = build_child_formset(
        family=family,
        post_data=request.POST if request.method == "POST" else None
    )

    if request.method == "POST":
        if child_formset.is_valid():

            if not family:
                creator_role = (
                    "lawyer_a"
                    if profile.role == "lawyer"
                    else "parent"
                )

                family = Family.objects.create(
                    name=f"Family {user.last_name}",
                    created_by=user,
                    creator_role=creator_role
                )

                member_role = (
                    "lawyer_a"
                    if profile.role == "lawyer"
                    else "parent_a"
                )

                FamilyMember.objects.create(
                    family=family,
                    user=user,
                    role=member_role,
                    is_primary=True
                )

            save_children(
                child_formset,
                family,
                user
            )

            complete_setup(profile)

            return redirect("families:summary")

    return {
        "context": {
            "form_user": FirstLoginForm(instance=user),
            "form_profile": UserProfileForm(instance=profile),
            "formset": child_formset,
            "is_setup": True,
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