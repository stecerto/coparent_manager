from django.urls import path

from families.views import family_summary, lawyer_expenses_dashboard_view
from .views import (
    approve_expense_view,
    dashboard_view,

    setup_view,
    invite_member_view,
    accept_invite_view, resend_invitation_view, cancel_invitation_view, confirm_invitation_view, expenses_by_child,
    invitation_landing_view, family_timeline_view, create_support_agreement_view, edit_support_agreement_view,
    delete_support_agreement_view, lawyer_dashboard_view
)

app_name = "families"

urlpatterns = [

    # =========================
    # DASHBOARD
    # =========================
    path("dashboard/", dashboard_view, name="family_dashboard"),
    path("lawyer/dashboard/", lawyer_dashboard_view, name="lawyer_dashboard"),
    path("summary/", family_summary, name="summary"),

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
        "expenses/<int:expense_id>/approve/", approve_expense_view, name="approve_expense"),

    path("invite/resend/<int:invitation_id>/", resend_invitation_view, name="invite_resend"),
    path("invite/cancel/<int:invitation_id>/", cancel_invitation_view, name="invite_cancel"),
    path("timeline/", family_timeline_view, name="timeline"),
    path("by-child/", expenses_by_child, name="expenses_by_child"),
#  ACCORDI DI MANTENIMENTO
    path("agreement/create/", create_support_agreement_view, name="create_support_agreement"),
    path("agreement/<int:agreement_id>/edit/", edit_support_agreement_view, name="edit_support_agreement"),
    path("agreement/<int:agreement_id>/delete/", delete_support_agreement_view, name="delete_support_agreement"),

    path('lawyer/expenses/', lawyer_expenses_dashboard_view, name='lawyer_expenses'),
    path('lawyer/expenses/<int:family_id>/', lawyer_expenses_dashboard_view, name='lawyer_expenses'),

]
