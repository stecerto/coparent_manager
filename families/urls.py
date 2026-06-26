from django.urls import path
from . import views

app_name = 'families'

urlpatterns = [
    # ========================================
    # 🏠 DASHBOARD PRINCIPALI
    # ========================================
    path('dashboard/', views.dashboard_view, name='family_dashboard'),
    path('setup/', views.setup_view, name='setup'),
    path('summary/', views.family_summary, name='summary'),
    path('settings/', views.family_settings_view, name='family_settings'),

    # ========================================
    # 👔 DASHBOARD PROFESSIONISTI (ROUTING INTELLIGENTE)
    # ========================================
    # ✅ Questa view ora fa routing automatico in base al ruolo:
    #    - lawyer → lawyer_dashboard.html
    #    - mediator → mediator_dashboard.html
    #    - consultant → consultant_dashboard.html
    path('professional/', views.professional_dashboard, name='professional_dashboard'),  # ✅ DECOMMENTATA

    # Eventi/documenti pendenti trasversali
    path('professional/pending/', views.professional_pending_events_view, name='professional_pending_events'),

    # ✅ NUOVO: Dashboard specifiche (opzionali, se vuoi URL dedicati)
    path('professional/lawyer/', views.lawyer_dashboard_view, name='lawyer_dashboard'),
    path('professional/mediator/', views.mediator_dashboard_view, name='mediator_dashboard'),
    path('professional/consultant/', views.consultant_dashboard_view, name='consultant_dashboard'),

    # ========================================
    # 🔄 CONTESTO FAMIGLIA (Switch/Exit)
    # ========================================
    path('set-active/<int:family_id>/', views.set_active_family, name='set_active_family'),
    #path('exit-context/', views.exit_family_context, name='exit_family_context'),
    path('lawyer-exit-context/', views.lawyer_exit_family_context, name='lawyer_exit_family_context'),

    # ========================================
    # 👨‍👩‍👧 FIGLI
    # ========================================
    path('children/edit/<int:child_id>/', views.edit_child_support_view, name='edit_child_support'),
    path('children/decree/<int:support_id>/', views.view_decree_view, name='view_decree'),

    # ========================================
    # 💰 SPESE (Vista Avvocato)
    # ========================================
    path('lawyer/expenses/', views.lawyer_expenses_dashboard_view, name='lawyer_expenses'),
    path('lawyer/expenses/<int:family_id>/', views.lawyer_expenses_dashboard_view, name='lawyer_expenses_family'),

    # ========================================
    # 💼 MANTENIMENTO CONIUGE
    # ========================================
    path('spouse-support/', views.spouse_support_list, name='spouse_support_list'),
    path('spouse-support/create/', views.spouse_support_create, name='spouse_support_create'),
    path('spouse-support/edit/<int:pk>/', views.spouse_support_edit, name='spouse_support_edit'),
    path('spouse-support/decree/<int:agreement_id>/', views.view_spouse_decree_view, name='view_spouse_decree'),

    # ========================================
    # 📨 INVITI
    # ========================================
    path('invite/', views.invite_member_view, name='invite_member'),
    path('invite/accept/<uuid:token>/', views.accept_invite_view, name='accept_invite'),
    path('invite/landing/<uuid:token>/', views.invitation_landing_view, name='invitation_landing'),
    path('invite/confirm/<uuid:token>/', views.confirm_invitation_view, name='confirm_invitation'),
    path('invite/resend/<int:invitation_id>/', views.resend_invitation_view, name='resend_invitation'),
    path('invite/cancel/<int:invitation_id>/', views.cancel_invitation_view, name='cancel_invitation'),

    # ========================================
    # 📤 EXPORT
    # ========================================
    path('export/', views.export_family_data_view, name='export_family_data'),

    # ========================================
    # 📊 ALTRO
    # ========================================
    path('expenses/by-child/', views.expenses_by_child, name='expenses_by_child'),
    path('timeline/', views.family_timeline_view, name='family_timeline'),
    path('approve-expense/<int:expense_id>/', views.approve_expense_view, name='approve_expense'),
    path("exit-context/", views.lawyer_exit_family_context, name="exit_lawyer_context"),
]
