# accounts/admin.py

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.http import HttpResponse
import csv
from .models import UserProfile

User = get_user_model()


# =========================
# 🔍 FILTRI CUSTOM PER USERPROFILE
# =========================

class RoleListFilter(admin.SimpleListFilter):
    """Filtro custom per ruolo utente"""
    title = '👔 Ruolo'
    parameter_name = 'role'

    def lookups(self, request, model_admin):
        return [
            ('parent_a', 'Genitore A'),
            ('parent_b', 'Genitore B'),
            ('lawyer_a', 'Avvocato A'),
            ('lawyer_b', 'Avvocato B'),
            ('mediator', 'Mediatore'),
            ('consultant', 'Consulente'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(profile__role=self.value())
        return queryset


class PlanListFilter(admin.SimpleListFilter):
    """Filtro custom per piano abbonamento"""
    title = '💰 Piano'
    parameter_name = 'plan'

    def lookups(self, request, model_admin):
        return [
            ('starter', 'Starter'),
            ('pro', 'Pro'),
            ('enterprise', 'Enterprise'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(profile__plan=self.value())
        return queryset


class SetupCompleteListFilter(admin.SimpleListFilter):
    """Filtro custom per stato setup"""
    title = '✅ Setup Completo'
    parameter_name = 'setup_complete'

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Completo'),
            ('no', 'Incompleto'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(profile__setup_complete=True)
        if self.value() == 'no':
            return queryset.filter(profile__setup_complete=False)
        return queryset


# =========================
# 📋 INLINE PER USERPROFILE
# =========================

class UserProfileInline(admin.StackedInline):
    """Inline per mostrare il profilo utente nell'admin"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profilo Utente'
    fk_name = 'user'

    fieldsets = (
        ('👤 Dati Personali', {
            'fields': ('role', 'phone', 'address', 'birth_date', 'birth_place', 'birth_place_code', 'codice_fiscale')
        }),
        ('💼 Dati Professionali', {
            'fields': ('firm_name', 'partita_iva'),
            'classes': ('collapse',)
        }),
        ('💰 Abbonamento', {
            'fields': ('plan', 'plan_started_at', 'plan_expires_at', 'payment_status')
        }),
        ('🔒 Sicurezza', {
            'fields': ('setup_complete', 'privacy_accepted_at', 'privacy_version_accepted')
        }),
    )

    readonly_fields = ('codice_fiscale', 'privacy_accepted_at')

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('role',)
        return self.readonly_fields


# =========================
# 👤 ADMIN USER CUSTOM
# =========================

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin custom per modello User con profilo integrato"""

    inlines = (UserProfileInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('profile')
        return qs

    list_display = (
        'email',
        'first_name',
        'last_name',
        'get_role_badge',
        'get_plan_badge',
        'is_active',
        'date_joined',
        'last_login',
        'get_setup_status'
    )

    list_filter = (
        'is_active',
        'is_staff',
        RoleListFilter,
        PlanListFilter,
        SetupCompleteListFilter,
        'date_joined',
        'last_login'
    )

    search_fields = (
        'email',
        'first_name',
        'last_name',
        'profile__codice_fiscale',
        'profile__phone',
        'profile__firm_name'
    )

    ordering = ('-date_joined',)

    actions = [
        'export_users_csv',
        'export_active_users_csv',
        'export_professionals_csv',
        'activate_users',
        'deactivate_users'
    ]

    fieldsets = (
        ('🔐 Credenziali', {
            'fields': ('email', 'username', 'password')
        }),
        ('👤 Informazioni Personali', {
            'fields': ('first_name', 'last_name')
        }),
        ('🔒 Permessi', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('📅 Date Importanti', {
            'fields': ('date_joined', 'last_login'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        ('🆕 Nuovo Utente', {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2', 'first_name', 'last_name'),
        }),
    )

    readonly_fields = ('date_joined', 'last_login')

    # ✅ CORRETTO: format_html con argomenti

    def get_role_badge(self, obj):
        """Badge colorato per ruolo utente"""
        try:
            profile = getattr(obj, 'profile', None)
            if not profile:
                # ✅ CORRETTO: usa mark_safe o format_html con args
                return format_html('<span class="badge bg-secondary">{}</span>', 'N/A')

            role = profile.role
            role_colors = {
                'parent_a': 'primary',
                'parent_b': 'primary',
                'lawyer_a': 'danger',
                'lawyer_b': 'danger',
                'mediator': 'warning',
                'consultant': 'info'
            }
            color = role_colors.get(role, 'secondary')
            display_role = role.replace('_', ' ').title() if role else 'N/A'
            return format_html('<span class="badge bg-{}">{}</span>', color, display_role)
        except Exception:
            return format_html('<span class="badge bg-secondary">{}</span>', 'N/A')

    get_role_badge.short_description = '👔 Ruolo'

    def get_plan_badge(self, obj):
        """Badge colorato per piano abbonamento"""
        try:
            profile = getattr(obj, 'profile', None)
            if not profile:
                return format_html('<span class="badge bg-secondary">{}</span>', 'N/A')

            plan = profile.plan
            plan_colors = {
                'starter': 'secondary',
                'pro': 'success',
                'enterprise': 'warning'
            }
            color = plan_colors.get(plan, 'secondary')
            display_plan = plan.upper() if plan else 'N/A'
            return format_html('<span class="badge bg-{}">{}</span>', color, display_plan)
        except Exception:
            return format_html('<span class="badge bg-secondary">{}</span>', 'N/A')

    get_plan_badge.short_description = '💰 Piano'

    def get_setup_status(self, obj):
        """Status completamento setup"""
        try:
            profile = getattr(obj, 'profile', None)
            if not profile:
                return format_html('<span class="badge bg-secondary">{}</span>', 'N/A')

            if profile.setup_complete:
                return format_html('<span class="badge bg-success">{}</span>', '✓ Completo')
            else:
                return format_html('<span class="badge bg-warning">{}</span>', '⚠ Incompleto')
        except Exception:
            return format_html('<span class="badge bg-secondary">{}</span>', 'N/A')

    get_setup_status.short_description = '✅ Setup'

    def export_users_csv(self, request, queryset):
        """Export tutti utenti in CSV"""
        queryset = queryset.select_related('profile')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="utenti_coparentmanager.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Email', 'Nome', 'Cognome', 'Ruolo', 'Piano',
            'Attivo', 'Setup Completo', 'Data Registrazione',
            'Codice Fiscale', 'Telefono', 'Studio'
        ])

        for user in queryset:
            try:
                profile = getattr(user, 'profile', None)
                if profile:
                    writer.writerow([
                        user.email,
                        user.first_name,
                        user.last_name,
                        profile.role or 'N/A',
                        profile.plan or 'N/A',
                        'Sì' if user.is_active else 'No',
                        'Sì' if profile.setup_complete else 'No',
                        user.date_joined.strftime('%d/%m/%Y %H:%M'),
                        profile.codice_fiscale or '',
                        profile.phone or '',
                        profile.firm_name or ''
                    ])
                else:
                    writer.writerow([
                        user.email,
                        user.first_name,
                        user.last_name,
                        'N/A', 'N/A',
                        'Sì' if user.is_active else 'No',
                        'N/A',
                        user.date_joined.strftime('%d/%m/%Y %H:%M'),
                        '', '', ''
                    ])
            except Exception:
                writer.writerow([
                    user.email,
                    user.first_name,
                    user.last_name,
                    'ERROR', 'ERROR',
                    'Sì' if user.is_active else 'No',
                    'ERROR',
                    user.date_joined.strftime('%d/%m/%Y %H:%M'),
                    '', '', ''
                ])

        return response

    export_users_csv.short_description = "📥 Export CSV tutti utenti"

    def export_active_users_csv(self, request, queryset):
        """Export solo utenti attivi"""
        active_users = queryset.filter(is_active=True)
        return self.export_users_csv(request, active_users)

    export_active_users_csv.short_description = "📥 Export CSV utenti attivi"

    def export_professionals_csv(self, request, queryset):
        """Export solo professionisti"""
        professionals = queryset.filter(
            profile__role__in=['lawyer_a', 'lawyer_b', 'mediator', 'consultant']
        )
        return self.export_users_csv(request, professionals)

    export_professionals_csv.short_description = "📥 Export CSV professionisti"

    def activate_users(self, request, queryset):
        """Attiva utenti selezionati"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'✅ {count} utenti attivati')

    activate_users.short_description = "✅ Attiva utenti selezionati"

    def deactivate_users(self, request, queryset):
        """Disattiva utenti selezionati"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'⚠️ {count} utenti disattivati')

    deactivate_users.short_description = "⚠️ Disattiva utenti selezionati"


# =========================
# 👤 ADMIN USERPROFILE STANDALONE
# =========================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin standalone per UserProfile"""

    list_display = (
        'user_email',
        'get_role_badge',
        'get_plan_badge',
        'setup_complete',
        'phone',
        'firm_name'
    )

    list_filter = (
        'role',
        'plan',
        'setup_complete',
        'payment_status'
    )

    search_fields = (
        'user__email',
        'user__first_name',
        'user__last_name',
        'codice_fiscale',
        'phone',
        'firm_name'
    )

    readonly_fields = ('user', 'codice_fiscale')

    def user_email(self, obj):
        return obj.user.email

    user_email.short_description = '📧 Email'
    user_email.admin_order_field = 'user__email'

    # ✅ CORRETTO: format_html con argomenti

    def get_role_badge(self, obj):
        role_colors = {
            'parent_a': 'primary',
            'parent_b': 'primary',
            'lawyer_a': 'danger',
            'lawyer_b': 'danger',
            'mediator': 'warning',
            'consultant': 'info'
        }
        color = role_colors.get(obj.role, 'secondary')
        display_role = obj.role.replace('_', ' ').title() if obj.role else 'N/A'
        return format_html('<span class="badge bg-{}">{}</span>', color, display_role)

    get_role_badge.short_description = '👔 Ruolo'

    def get_plan_badge(self, obj):
        plan_colors = {
            'starter': 'secondary',
            'pro': 'success',
            'enterprise': 'warning'
        }
        color = plan_colors.get(obj.plan, 'secondary')
        display_plan = obj.plan.upper() if obj.plan else 'N/A'
        return format_html('<span class="badge bg-{}">{}</span>', color, display_plan)

    get_plan_badge.short_description = '💰 Piano'