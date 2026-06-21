from django.urls import path
from django.views.generic import RedirectView

from families.views import family_summary, lawyer_expenses_dashboard_view, professional_dashboard, set_active_family, \
    lawyer_exit_family_context, exit_family_context, professional_pending_events_view, spousal_support_view, \
    family_settings_view, export_family_data_view, spouse_support_edit, spouse_support_create, \
    spouse_support_list, edit_child_support_view, view_decree_view, view_spouse_decree_view
from chat.views import delete_message_view
from .views import (approve_expense_view, dashboard_view, setup_view, invite_member_view,
    accept_invite_view, resend_invitation_view, cancel_invitation_view, confirm_invitation_view, expenses_by_child,
    invitation_landing_view, family_timeline_view

)

app_name = "families"

urlpatterns = [

    # =========================
    # DASHBOARD
    # =========================
    path("dashboard/", dashboard_view, name="family_dashboard"),

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
    path("message/<int:pk>/delete/", delete_message_view, name="delete_message"),
    path("accept-invite/<str:token>/", accept_invite_view, name="accept_invite"),
    path("spousal-support/", spousal_support_view, name="spousal_support"),
    path('family-settings/', family_settings_view, name='family_settings'),
    path('child-support/<int:child_id>/edit/', edit_child_support_view, name='edit_child_support'),
    path('export-data/', export_family_data_view, name='export_family_data'),
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
    path('decree/<int:support_id>/', view_decree_view, name='view_decree'),
    path('spouse-support/<int:agreement_id>/decree/', view_spouse_decree_view, name='view_spouse_decree'),



    path('lawyer/expenses/', lawyer_expenses_dashboard_view, name='lawyer_expenses'),
    path('lawyer/expenses/<int:family_id>/', lawyer_expenses_dashboard_view, name='lawyer_expenses'),

    path('professional/dashboard/', professional_dashboard, name='professional_dashboard'),
    path('professional/pending-events/', professional_pending_events_view, name='professional_pending_events'),
    path('set-active/<int:family_id>/', set_active_family, name='set_active_family'),
    path("families/exit-lawyer-context/", lawyer_exit_family_context, name="exit_lawyer_context"),
    path("families/exit-context/", exit_family_context, name="exit_family_context"),
    # 🔄 Redirect delle vecchie route (compatibilità)
    path('lawyer/home/', RedirectView.as_view(pattern_name='lawyer_home', permanent=False),
         name='lawyer_home'),
    path('mediator/home/', RedirectView.as_view(pattern_name='lawyer_home', permanent=False),
         name='mediator_home'),
    path('consultant/home/', RedirectView.as_view(pattern_name='lawyer_home', permanent=False),
         name='consultant_home'),

    # Mantenimento Coniuge
    path('spouse-support/', spouse_support_list, name='spouse_support_list'),
    path('spouse-support/create/', spouse_support_create, name='spouse_support_create'),
    path('spouse-support/<int:pk>/edit/', spouse_support_edit, name='spouse_support_edit'),

]
