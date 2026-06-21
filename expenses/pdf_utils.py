# expenses/pdf_utils.py
import os
from datetime import datetime
from decimal import Decimal

from django.template.loader import render_to_string
from weasyprint import HTML

from config import settings


def generate_expense_report_pdf(request, family, expenses, total_expenses, parent_a_total, parent_b_total):
    from decimal import Decimal
    from families.models import FamilyMember

    # ✅ FILTRA solo spese attive (evita versioni archiviate duplicate)
    expenses = [exp for exp in expenses if exp.is_active]

    # 🧮 Calcola quote per ogni spesa
    for exp in expenses:
        pct_raw = getattr(exp.child, 'contribution_pct_parent_a', None) if exp.child else None
        pct_a = Decimal(str(pct_raw)) if pct_raw is not None else Decimal('50.00')
        exp.quota_a = exp.amount * (pct_a / Decimal('100'))
        exp.quota_b = exp.amount * ((Decimal('100') - pct_a) / Decimal('100'))

    # ✅ SEPARA le spese
    ordinary_expenses = [exp for exp in expenses if exp.group_snapshot == "ordinarie"]
    extraordinary_expenses = [exp for exp in expenses if exp.group_snapshot != "ordinarie"]

    # ✅ Calcola totali
    ordinary_total = sum(exp.amount for exp in ordinary_expenses) or Decimal("0.00")
    extraordinary_total = sum(exp.amount for exp in extraordinary_expenses) or Decimal("0.00")
    extraordinary_parent_a = sum(exp.quota_a for exp in extraordinary_expenses) or Decimal("0.00")
    extraordinary_parent_b = sum(exp.quota_b for exp in extraordinary_expenses) or Decimal("0.00")

    # ✅ RECUPERA NOMI GENITORI (con fallback robusto)
    parent_a_name = "Genitore A"
    parent_b_name = "Genitore B"

    # Prova prima con i ruoli specifici
    parent_a_member = FamilyMember.objects.filter(
        family=family,
        role__in=["parent_a", "parent"]
    ).select_related('user').first()

    parent_b_member = FamilyMember.objects.filter(
        family=family,
        role__in=["parent_b", "parent"]
    ).exclude(user=parent_a_member.user if parent_a_member else None).select_related('user').first()

    if parent_a_member and parent_a_member.user:
        full_name = parent_a_member.user.get_full_name().strip()
        parent_a_name = full_name if full_name else parent_a_member.user.email

    if parent_b_member and parent_b_member.user:
        full_name = parent_b_member.user.get_full_name().strip()
        parent_b_name = full_name if full_name else parent_b_member.user.email

    # ✅ Costruisci URL assoluto corretto per WeasyPrint
    logo_file_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo-coparent.svg')
    logo_url = f'file://{logo_file_path}'

    # Debug: stampa l'URL generato
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"📄 Logo URL: {logo_url}")

    context = {
        "family": family,
        "user": request.user,
        "expenses": expenses,
        "ordinary_expenses": ordinary_expenses,
        "extraordinary_expenses": extraordinary_expenses,
        "total_expenses": total_expenses,
        "ordinary_total": ordinary_total,
        "extraordinary_total": extraordinary_total,
        "parent_a_total": parent_a_total,
        "parent_b_total": parent_b_total,
        "extraordinary_parent_a": extraordinary_parent_a,
        "extraordinary_parent_b": extraordinary_parent_b,
        "parent_a_name": parent_a_name,
        "parent_b_name": parent_b_name,
        "generation_date": datetime.now(),
        "logo_url": logo_url,
    }

    html_string = render_to_string("reports/expenses_report.html", context, request=request)
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()
    return pdf_file


'''
def generate_expense_report(user):
    family = get_family_of_user(user)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4
    y = height - 50

    # 📌 titolo
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, f"Report Spese Famiglia {user.last_name} {user.first_name}")
    y -= 40

    expenses = Expense.objects.filter(
        family=family,
        is_active=True
    ).order_by("-expense_date")

    # 💰 TOTALE SPESE (FIX IMPORTANTE)
    total_expenses = expenses.aggregate(
        total=Sum("amount")
    )["total"] or 0

    pdf.setFont("Helvetica", 10)

    # 📄 LISTA SPESE
    for expense in expenses:
        if y < 50:
            pdf.showPage()
            y = height - 50

        line = (
            f"{expense.child} | "
            f"{expense.created_by} | "
            f"{expense.expense_date} | "
            f"{expense.expense_type.name} | "
            f"{expense.amount} € | "
            f"{expense.description}"
        )

        pdf.drawString(50, y, line)
        y -= 20

    # 📊 TOTALE IN FONDO
    if y < 80:
        pdf.showPage()
        y = height - 50

    y -= 30
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, f"Totale spese: {total_expenses} €")

    pdf.save()
    buffer.seek(0)

    return buffer
'''