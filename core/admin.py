from django import forms
from django.contrib import admin
from .models import DashboardWidget, Payment


class DashboardWidgetAdminForm(forms.ModelForm):

    target_roles = forms.MultipleChoiceField(
        choices=[
            ("parent", "Genitore"),
            ("lawyer", "Avvocato"),
            ("mediator", "Mediatore"),
            ("consultatn", "Consulente"),
        ],
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    allowed_plan_levels = forms.MultipleChoiceField(
        choices=[
            (1, "Starter"),
            (2, "Pro"),
            (3, "Enterprise"),
        ],
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = DashboardWidget
        fields = "__all__"

    def clean_target_roles(self):
        return self.cleaned_data["target_roles"]

    def clean_allowed_plan_levels(self):
        return [
            int(v)
            for v in self.cleaned_data["allowed_plan_levels"]
        ]


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):

    form = DashboardWidgetAdminForm

    list_display = (
        'title',
        'widget_key',
        'get_target_roles',
        'get_plan_levels',
        'position',
        'is_active'
    )

    list_filter = (
        'is_active',
        'allowed_plan_levels'
    )

    search_fields = (
        'title',
        'widget_key'
    )

    ordering = (
        'position',
        'title'
    )

    fieldsets = (
        (
            'Informazioni Base',
            {
                'fields': (
                    'title',
                    'widget_key',
                    'is_active'
                )
            }
        ),
        (
            'Visibilità',
            {
                'fields': (
                    'target_roles',
                    'allowed_plan_levels'
                )
            }
        ),
        (
            'Ordinamento',
            {
                'fields': (
                    'position',
                )
            }
        ),
    )

    def get_target_roles(self, obj):
        return ", ".join(obj.target_roles) if obj.target_roles else "Tutti"

    get_target_roles.short_description = "Ruoli Target"

    def get_plan_levels(self, obj):
        mapping = {
            1: "Starter",
            2: "Pro",
            3: "Enterprise"
        }

        return ", ".join(
            mapping.get(i, str(i))
            for i in obj.allowed_plan_levels
        )

    get_plan_levels.short_description = "Piani"

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'amount', 'status', 'payment_date')
    list_filter = ('status', 'currency')
    search_fields = ('subscription__user__email', 'transaction_id')