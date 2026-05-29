import os
from django.conf import settings
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


def generate_child_report(child, supports):
    folder = os.path.join(settings.MEDIA_ROOT, "report_pdf")

    # crea cartella se non esiste
    os.makedirs(folder, exist_ok=True)

    file_name = f"report_child_{child.id}.pdf"

    file_path = os.path.join(folder, file_name)

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    content = []

    content.append(Paragraph(f"Report Figlio: {child.name.capitalize()}", styles["Title"]))
    content.append(Spacer(1, 10))

    content.append(Paragraph("Storico mantenimento:", styles["Heading2"]))
    content.append(Spacer(1, 10))

    for s in supports:
        text = f"{s.amount} € dal {s.start_date}"
        if s.end_date:
            text += f" al {s.end_date}"
        else:
            text += " (attuale)"

        content.append(Paragraph(text, styles["Normal"]))
        content.append(Spacer(1, 5))

    doc.build(content)

    return file_path