# accounts/utils.py


from accounts.models import UserProfile
import codicefiscale

# =========================
# UTENTE / PROFILO
# =========================
def get_user_profile(user):
    """Restituisce il profilo dell'utente, crea se non esiste"""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def is_setup_complete(user):
    """Controlla se l'utente ha completato il setup"""
    profile = get_user_profile(user)
    return profile.setup_complete


# accounts/utils/fiscal_cod
import codicefiscale
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)
def generate_cf(first_name, last_name, birth_date, birth_place_code, gender):

    if not all([first_name, last_name, birth_date, birth_place_code, gender]):
        return None

    # 🔥 FIX CRITICO: normalizzazione data
    if isinstance(birth_date, str):
        try:
            birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
        except:
            return None

    # 👉 CONVERSIONE OBBLIGATORIA IN STRINGA ITALIANA
    birth_date_str = birth_date.strftime("%d/%m/%Y")

    gender = str(gender).upper()
    if gender not in ["M", "F"]:
        return None
    birth_place_code = str(birth_place_code).upper().strip()

    try:
        return codicefiscale.encode(
            lastname=last_name,
            firstname=first_name,
            birthdate=birth_date_str,   # ✔ ORA STRINGA
            gender=gender,
            birthplace=birth_place_code
        )
    except Exception as e:
        logger.error(f"CF error: {e}")
        return None




def validate_cf(cf):
    """Valida un codice fiscale esistente."""
    try:
        return codicefiscale.is_valid(cf)
    except Exception:
        return False


# accounts/utils.py - SOSTITUISCI le funzioni esistenti

def load_comuni_json():
    """
    Carica i comuni italiani dal database.
    Mantiene la stessa signature per retrocompatibilità.

    Returns:
        list: Lista di dizionari con chiavi 'nome', 'codice_catastale', 'provincia'
    """
    from accounts.models import Comune

    try:
        comuni = list(Comune.objects.values('nome', 'codice_catastale', 'provincia'))
        logger.info(f"✅ Caricati {len(comuni)} comuni dal database")
        return comuni
    except Exception as e:
        logger.error(f"❌ Errore caricamento comuni dal DB: {e}")
        return []


def search_comuni(query, limit=50):
    """
    Cerca comuni per nome, codice catastale o provincia usando il database.

    Args:
        query: Stringa da cercare (min 2 caratteri)
        limit: Numero massimo di risultati (default 50)

    Returns:
        list: Lista di dizionari con 'id' e 'text' (formato Select2)
    """
    from accounts.models import Comune
    from django.db.models import Q

    query = query.strip()

    if len(query) < 2:
        return []

    try:
        # Cerca in nome, codice o provincia
        comuni = Comune.objects.filter(
            Q(nome__icontains=query) |
            Q(codice_catastale__icontains=query) |
            Q(provincia__icontains=query)
        )[:limit]

        results = []
        for comune in comuni:
            results.append({
                'id': comune.codice_catastale,
                'text': f"{comune.nome} ({comune.codice_catastale}) - {comune.provincia}"
            })

        return results
    except Exception as e:
        logger.error(f"❌ Errore ricerca comuni: {e}")
        return []


def get_comune_name(codice_catastale):
    """
    Ottiene il nome del comune dato il codice catastale.

    Args:
        codice_catastale: Codice catastale (es: "H501")

    Returns:
        str: Nome del comune o stringa vuota se non trovato
    """
    from accounts.models import Comune

    try:
        comune = Comune.objects.filter(codice_catastale=codice_catastale).first()
        return comune.nome if comune else ""
    except Exception as e:
        logger.error(f"❌ Errore ricerca comune per codice {codice_catastale}: {e}")
        return ""