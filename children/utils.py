from datetime import datetime

from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from children.models import ChildProfile
from accounts.utils import get_user_profile


def archive_child(child: ChildProfile, modified_by_user):
    """Marca un figlio come archiviato senza cancellarlo"""
    child.is_active = False
    child.archived_at = timezone.now()
    child.modified_by = modified_by_user
    child.save()
    return child


# =========================
# FIGLI
# =========================
def get_active_children(user):
    """Restituisce la lista dei figli attivi dell'utente"""
    family = get_user_profile(user)

    return family.children.filter(is_active=True)


def get_child_split_pct(child):
    """
    Restituisce la percentuale di ripartizione per un figlio.
    Priorità: contribution_pct_parent_a → fallback a 50.00
    """
    if child and child.contribution_pct_parent_a is not None:
        return float(child.contribution_pct_parent_a)
    return 50.00  # Fallback sicuro


def calculate_expense_shares(child, amount):
    """
    Calcola le quote di una spesa dato l'importo e il figlio.
    Returns: (quota_a, quota_b) come float arrotondati a 2 decimali
    """
    if not child or not amount:
        return 0.0, 0.0

        # ✅ Clamp e fallback sicuro
    pct_a = float(getattr(child, 'contribution_pct_parent_a', None) or 50.0)
    pct_a = max(0.0, min(100.0, pct_a))
    pct_b = 100.0 - pct_a

    return round(amount * (pct_a / 100), 2), round(amount * (pct_b / 100), 2)


# children/pdf_utils.py
from django.template.loader import render_to_string
from weasyprint import HTML
from datetime import datetime

import os
from datetime import datetime
from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML


def generate_child_report_pdf(child, current_support, expenses_data, approved_total, parent_a_total, parent_b_total,
                              split_a, split_b, balance, request):
    # ✅ Percorso ASSOLUTO al logo (WeasyPrint lo legge direttamente dal disco)
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo-coparent.svg')

    context = {
        "child": child,
        "current_support": current_support,
        "expenses": expenses_data,
        "approved_total": approved_total,
        "parent_a_total": parent_a_total,
        "parent_b_total": parent_b_total,
        "split_a": split_a,
        "split_b": split_b,
        "balance": balance,
        "generation_date": datetime.now(),
        "logo_path": logo_path if os.path.exists(logo_path) else "",
    }

    html_string = render_to_string("reports/child_report.html", context, request=request)

    # ✅ base_url non serve più per il logo, ma lascialo per eventuali CSS/Font relativi
    return HTML(string=html_string, base_url=os.path.join(settings.BASE_DIR, 'static')).write_pdf()