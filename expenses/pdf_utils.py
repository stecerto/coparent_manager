# expenses/pdf_utils.py
from datetime import datetime
from decimal import Decimal

from django.template.loader import render_to_string
from weasyprint import HTML

from config import settings


def generate_expense_report_pdf(request, family, expenses, total_expenses, parent_a_total, parent_b_total):
    # 🧮 Calcola quote per ogni spesa (CONVERSIONE SICURA A DECIMAL)
    for exp in expenses:
        pct_raw = getattr(exp.child, 'contribution_pct_parent_a', None)
        # ✅ Converti esplicitamente a Decimal per evitare TypeError
        pct_a = Decimal(str(pct_raw)) if pct_raw is not None else Decimal('50.00')

        exp.quota_a = exp.amount * (pct_a / Decimal('100'))
        exp.quota_b = exp.amount * ((Decimal('100') - pct_a) / Decimal('100'))
    logo_url = request.build_absolute_uri(settings.STATIC_URL + "images/icon-192x192.png")
    context = {
        "family": family, "user": request.user, "expenses": expenses,
        "total_expenses": total_expenses, "parent_a_total": parent_a_total,
        "parent_b_total": parent_b_total, "generation_date": datetime.now(),
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