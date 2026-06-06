import re
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from documents.models import Document
from documents.services.pdf_service import extract_pdf_date
from documents.services.pdf_service import extract_text_from_pdf
from families.utils import get_family_of_user


def validate_income_documents(user):
    payslips = Document.objects.filter(user=user, document_type="payslip")
    tax = Document.objects.filter(user=user, document_type="tax_return")

    return payslips.count() >= 3 and tax.count() >= 3


@login_required
def upload_income_documents(request):

    family = get_family_of_user(request.user, request=request)

    if request.method == "POST":
        files = request.FILES.getlist("files")
        doc_type = request.POST.get("type")
        year = request.POST.get("year")

        for f in files:

            doc = Document.objects.create(
                user=request.user,
                family=family,
                file=f,
                document_type=doc_type,
                referenze_year=year
            )
            pdf_date = extract_pdf_date(doc.file.path)

            if pdf_date:
                doc.document_date = datetime.strptime(pdf_date, "%d/%m/%Y").date()
                doc.save()
                print(pdf_date)

    docs = Document.objects.filter(user=request.user)

    return render(request, "accounts/income_upload.html", {"docs": docs})


def calculate_income(user):
    docs = Document.objects.filter(user=user)

    if not docs.exists():
        return 0

    values = []

    for doc in docs:
        amount = extract_amount(doc)
        if amount:
            values.append(amount)

    if not values:
        return 0

    return sum(values) / len(values)



def extract_amount(document):
    text = extract_text_from_pdf(document.file.path)

    match = re.search(r"\d+[.,]\d{2}", text)

    if match:
        return float(match.group().replace(",", "."))

    return None