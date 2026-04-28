import pdfplumber
import re
from datetime import datetime
import pytesseract
from pdf2image import convert_from_path


def extract_amount(document):
    text = extract_text_from_pdf(document.file.path)

    match = re.search(r"\d+[.,]\d{2}", text)

    if match:
        return float(match.group().replace(",", "."))

    return None


def extract_text_from_pdf(pdf_path):
    text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    return text


def extract_date_from_text(text):
    """
    Cerca date in vari formati:
    31/01/2025
    31-01-2025
    2025-01-31
    """

    patterns = [
        r"\b\d{2}/\d{2}/\d{4}\b",
        r"\b\d{2}-\d{2}-\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group()

    return None


def extract_pdf_date(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    return extract_date_from_text(text)

def extract_text_with_ocr(pdf_path):
    text = ""

    images = convert_from_path(pdf_path)

    for image in images:
        text += pytesseract.image_to_string(image)

    return text


def extract_pdf_text_smart(pdf_path):
    text = extract_text_from_pdf(pdf_path)

    if text.strip():
        return text

    # fallback OCR
    return extract_text_with_ocr(pdf_path)