from django.urls import path

from .views import (
    approve_expense_view,
    dashboard_view,
    summary_view,
    setup_view,
    invite_member_view,
    accept_invite_view, resend_invitation_view, cancel_invitation_view, confirm_invitation_view, expenses_by_child,
    invitation_landing_view, family_timeline_view,
)

app_name = "families"

urlpatterns = [

    # =========================
    # DASHBOARD
    # =========================
    path("dashboard/", dashboard_view, name="family_dashboard"),
    path("summary/", summary_view, name="summary"),

    # =========================
    # SETUP FAMIGLIA
    # =========================
    path("setup/", setup_view, name="setup"),

    # =========================
    # INVITI
    # =========================
    path("invite/", invite_member_view, name="invite_member"),
    path("invite/<str:token>/", invitation_landing_view, name="invitation_landing"),
    path("invite/<uuid:token>/confirm/", confirm_invitation_view, name="invite_confirm"),

    path("accept-invite/<str:token>/", accept_invite_view, name="accept_invite"),

    # =========================
    # EXPENSES
    # =========================
    path(
        "expenses/<int:expense_id>/approve/",
        approve_expense_view,
        name="approve_expense"
    ),

    path("invite/resend/<int:invitation_id>/", resend_invitation_view, name="invite_resend"),
    path("invite/cancel/<int:invitation_id>/", cancel_invitation_view, name="invite_cancel"),
    path("timeline/", family_timeline_view, name="timeline"),
    path("by-child/", expenses_by_child, name="expenses_by_child")
]
