from decimal import Decimal
from decimal import InvalidOperation

from django import forms
from django.forms import inlineformset_factory

from families.models import Family
from .models import ChildProfile


class ChildForm(forms.ModelForm):
    class Meta:
        model = ChildProfile
        # ✅ Mantieni i tuoi campi originali
        fields = ["name", "surname", "birth_date", "custody_type", "contribution_pct_parent_a", "manual_maintenance_amount", "notes"]

        # ✅ Etichette in italiano (senza toccare models)
        labels = {
            "name": "Nome",
            "surname": "Cognome",
            "birth_date": "Data di nascita",
            "custody_type": "Tipo affidamento",
            "contribution_pct_parent_a": "% Contributo Genitore A",
            "manual_maintenance_amount": "Mantenimento mensile (€)",
            "notes": "Note aggiuntive"
        }

        # ✅ Mantieni i tuoi widgets originali
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "custody_type": forms.Select(attrs={"class": "form-select"}),
            "contribution_pct_parent_a": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "max": "100", "class": "form-control"}),

            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"})
        }
        help_texts = {
            "manual_maintenance_amount": "Importo mensile fissato da accordo o sentenza. Il sistema gestirà lo storico automaticamente."
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ Rende i campi "non bloccanti" a livello HTML/POST
        self.fields['contribution_pct_parent_a'].required = False
        #self.fields['contribution_pct_parent_a'].initial = None
        self.fields['contribution_pct_parent_a'].widget.attrs.update({
            'placeholder': 'Es: 50', 'class': 'form-control'
        })
        for f in ['name', 'surname', 'birth_date', 'custody_type', 'contribution_pct_parent_a']:
            self.fields[f].required = False

    def clean(self):
        cleaned_data = super().clean()

        # 🛑 FIX CRITICO: Se è un form NUOVO e TUTTI i campi sono vuoti, salta la validazione
        if not self.instance.pk and not any(
                cleaned_data.get(f) for f in ['name', 'surname', 'birth_date', 'custody_type', "manual_maintenance_amount", 'notes']):
            return cleaned_data  # Django ignorerà questo form nel formset

        # ✅ Applica default SOLO se l'utente ha compilato almeno un campo
        cleaned_data['custody_type'] = cleaned_data.get('custody_type') or 'shared_custody'
        #if not cleaned_data.get('contribution_pct_parent_a'):
        #    cleaned_data['contribution_pct_parent_a'] = Decimal('50.00')

        return cleaned_data


    def clean_contribution_pct_parent_a(self):
        val = self.cleaned_data.get("contribution_pct_parent_a")
        if val in [None, "", ""]:
            # Fallback: valore esistente o default 50.00
            return self.instance.contribution_pct_parent_a if self.instance.pk else Decimal("50.00")
        try:
            val = Decimal(str(val).replace(",", "."))
            if not (Decimal("0") <= val <= Decimal("100")):
                self.add_error("contribution_pct_parent_a", "Valore tra 0 e 100")
            return val.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            self.add_error("contribution_pct_parent_a", "Formato non valido (es: 75.50)")


# ✅ Formset factory: usa Family come parent, ChildProfile come child
ChildFormSet = inlineformset_factory(
    Family,
    ChildProfile,
    form=ChildForm,  # ← Usa ChildForm, non ChildProfileForm (evita duplicati)
    extra=1,
    can_delete=True,
)


from django import forms

class ChildSupportForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

