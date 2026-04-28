from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from django.db.models import Sum

from expenses.models import Expense
from families.utils import get_family_of_user


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