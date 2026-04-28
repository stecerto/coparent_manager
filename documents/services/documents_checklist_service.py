from datetime import date
from documents.models import Document


def get_essential_checklist(user, family):
    current_year = date.today().year
    required_tax_year = current_year - 1

    payslips = len(
        Document.objects.filter(
            family=family,
            owner=user,
            category="payslip",
            reference_year=current_year,
            is_active=True
        ).order_by("-created_at")[:3]
    )

    tax_uploaded = Document.objects.filter(
        family=family,
        owner=user,
        category="tax_return",
        reference_year=required_tax_year,
        is_active=True
    ).exists()

    checklist = {
        "current_year": current_year,
        "required_tax_year": required_tax_year,
        "payslips_uploaded": payslips,
        "payslips_missing": max(0, 3 - payslips),
        "tax_uploaded": tax_uploaded,
    }

    return checklist