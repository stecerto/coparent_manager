from django import template
from families.models import FamilyMember

register = template.Library()


@register.filter(name="get_child_color")
def get_child_color(child):
    colors = [
        "primary",
        "success",
        "info",
        "warning",
        "danger",
        "dark",
        "secondary",
    ]

    child_id = getattr(child, "id", 0) or 0
    return colors[child_id % len(colors)]


@register.filter
def class_name(obj):
    return obj.__class__.__name__


@register.filter
def parent_display_name(family, role):
    if not family:
        return "Genitore A" if role == "parent_a" else "Genitore B"

    member = (
        FamilyMember.objects
        .filter(
            family=family,
            role__in=[role],
            user__is_active=True
        )
        .select_related("user")
        .first()
    )

    if member and member.user:
        return (
            member.user.get_full_name().strip()
            or member.user.email
        )

    return "Genitore A" if role == "parent_a" else "Genitore B"


@register.filter
def parent_short_name(family, role):
    full = parent_display_name(family, role)

    if full.startswith("Genitore"):
        return full

    return full.split()[0]