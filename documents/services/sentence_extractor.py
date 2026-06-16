# documents/services/sentence_extractor.py
import re
import logging
from .pdf_service import extract_text_from_pdf, extract_pdf_text_smart

logger = logging.getLogger(__name__)


def extract_sentence_data(document):
    """
    Estrae dati strutturati da un PDF di sentenza.
    Ritorna un dizionario con i dati trovati.
    """
    if not document.file or not document.file.name:
        return {}

    try:
        # Usa la funzione smart che fa fallback OCR se il PDF è scansionato
        text = extract_pdf_text_smart(document.file.path)
    except Exception as e:
        logger.error(f"Errore lettura PDF per doc {document.id}: {e}")
        return {}

    if not text or len(text.strip()) < 50:
        logger.warning(f"Testo estratto troppo corto per doc {document.id}")
        return {}

    data = {}

    # ✅ 1. MANTENIMENTO (cerca importi mensili)
    # Pattern: "€ 1.200,00", "euro 1200", "1.200,00 euro"
    maintenance_patterns = [
        r"(?:mantenimento|assegno|contributo)\s+(?:mensile|periodico)?\s*(?:di|pari a|importo)?\s*[€€]?\s*([\d.,]+)",
        r"[€€]\s*([\d.,]+)\s*(?:al mese|mensili|mensile)",
        r"(\d+[.,]\d{2})\s*(?:euro|€)",
    ]
    for pattern in maintenance_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(".", "").replace(",", ".")
            try:
                data["maintenance_amount"] = float(amount_str)
                break
            except ValueError:
                continue

    # ✅ 2. AFFIDAMENTO (cerca tipo di affidamento)
    custody_patterns = [
        r"affidamento\s+(condiviso|esclusivo|alternato)",
        r"(condiviso|esclusivo|alternato)\s+affidamento",
    ]
    for pattern in custody_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["custody_type"] = match.group(1).capitalize()
            break

    # ✅ 3. CASA FAMILIARE (cerca assegnazione)
    house_patterns = [
        r"assegnazione\s+(?:della\s+)?casa\s+(?:familiare)?\s+(?:a\s+favore\s+di|a|al\s+genitore)\s+([A-Z][a-z]+)",
        r"casa\s+(?:familiare)?\s+(?:viene\s+)?assegnata\s+(?:a|al)\s+([A-Z][a-z]+)",
        r"assegnata\s+(?:a\s+)?([A-Z][a-z]+)\s+(?:la\s+)?casa",
    ]
    for pattern in house_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["house_assigned_to"] = match.group(1)
            break

    # ✅ 4. VEICOLI (cerca assegnazione o divisione)
    vehicle_patterns = [
        r"(?:veicol[oi]|auto|automobil[ei])\s+(?:assegnat[oi]|divis[oi])\s+(?:a\s+)?([A-Z][a-z]+)",
        r"([A-Z][a-z]+)\s+(?:riceve|ottiene)\s+(?:l['']|il\s+)?(?:veicol[oi]|auto)",
    ]
    for pattern in vehicle_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["vehicle_assignment"] = match.group(1)
            break

    # ✅ 5. QUOTE GENITORI (cerca percentuali di mantenimento)
    quota_patterns = [
        r"([A-Z][a-z]+)\s+(?:al|nella misura del|per il)\s+(\d{1,3})\s*%",
        r"(\d{1,3})\s*%\s+(?:a carico di|per\s+)?([A-Z][a-z]+)",
    ]
    for pattern in quota_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            quotas = {}
            for match in matches:
                if match[0].isdigit():
                    quotas[match[1]] = int(match[0])
                else:
                    quotas[match[0]] = int(match[1])
            if quotas:
                data["parent_quotas"] = quotas
            break

    # ✅ 6. DATA SENTENZA
    date_patterns = [
        r"sentenza\s+(?:del|n\.|numero)?\s*(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["ruling_date"] = match.group(1)
            break

    # ✅ 7. NUMERO RG (Registro Generale)
    rg_patterns = [
        r"R\.?G\.?\s*(?:n\.?|numero)?\s*(\d+/\d{4})",
        r"(\d+/\d{4})\s*R\.?G\.?",
    ]
    for pattern in rg_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["rg_number"] = match.group(1)
            break

    logger.info(f"✅ Estratti dati da sentenza doc {document.id}: {list(data.keys())}")
    return data