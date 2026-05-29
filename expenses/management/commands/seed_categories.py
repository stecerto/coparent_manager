# expenses/management/commands/seed_categories.py
from django.core.management.base import BaseCommand

from expenses.models import (
    ExpenseCategoryGroup,
    ExpenseCategory
)

GROUPS = [
    ("ordinarie", "Ordinarie", "#28a745"),
    ("straordinarie", "Straordinarie", "#dc3545"),
    ("straordinarie_concordare", "Straordinarie da Concordare", "#ffc107"),
]

CATEGORIES = [

    # ORDINARIE
    ("ordinarie", "scuola_mensa", "Scuola, Mensa e Doposcuola", "#28a745"),

    ("ordinarie", "sport", "Sport e Attività Ricreative", "#17a2b8"),

    ("ordinarie", "abbigliamento", "Abbigliamento e Scarpe", "#ffc107"),

    # STRAORDINARIE
    ("straordinarie", "mediche", "Cure Mediche, Dentistiche e Specialistiche", "#dc3545"),

    ("straordinarie", "vacanze", "Vacanze, Gite e Campi Estivi", "#007bff"),

    # CONCORDARE
    ("straordinarie_concordare", "extrascolastiche",
     "Attività Extrascolastiche Costose (>200€/anno)", "#fd7e14"),
]


class Command(BaseCommand):

    help = "Seed categories"

    def handle(self, *args, **kwargs):

        groups = {}

        for code, label, color in GROUPS:

            group, _ = ExpenseCategoryGroup.objects.get_or_create(
                code=code,
                defaults={
                    "label": label,
                    "color": color
                }
            )

            groups[code] = group

        for group_code, slug, display_name, color in CATEGORIES:

            ExpenseCategory.objects.get_or_create(
                slug=slug,
                version=1,
                defaults={
                    "group": groups[group_code],
                    "display_name": display_name,
                    "color": color,
                    "is_active": True
                }
            )

        self.stdout.write(
            self.style.SUCCESS("Categorie create")
        )