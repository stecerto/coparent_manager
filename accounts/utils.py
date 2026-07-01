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


# accounts/utils/fiscal_code.py
import codicefiscale
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)


def generate_cf(first_name, last_name, birth_date, birth_place_code, gender):
    """
    Genera codice fiscale italiano usando python-codicefiscale.

    Args:
        first_name: Nome (es: "Mario")
        last_name: Cognome (es: "Rossi")
        birth_date: Data di nascita (date, datetime o stringa YYYY-MM-DD)
        birth_place_code: CODICE CATASTALE (es: "H501" per Roma)
        gender: "M" o "F"

    Returns:
        Codice fiscale in uppercase, oppure None se errore
    """
    try:
        if not all([first_name, last_name, birth_date, birth_place_code, gender]):
            return None

        # Normalizza birth_date in stringa YYYY-MM-DD
        if isinstance(birth_date, datetime):
            birth_date_str = birth_date.strftime('%Y-%m-%d')
        elif isinstance(birth_date, date):
            birth_date_str = birth_date.strftime('%Y-%m-%d')
        else:
            birth_date_str = str(birth_date)

        # Normalizza gender
        gender = str(gender).upper()
        if gender not in ['M', 'F']:
            return None

        # Normalizza codice catastale
        birth_place_code = str(birth_place_code).upper().strip()

        # Costruisci il codice fiscale pezzo per pezzo
        # Formato: COGNOME(3) + NOME(3) + ANNO(2) + MESE(1) + GIORNO(2) + CODICE(4) + CIN(1)

        # 1. Cognome (3 caratteri)
        cognome_cf = codicefiscale.encode_lastname(last_name.strip())

        # 2. Nome (3 caratteri)
        nome_cf = codicefiscale.encode_firstname(first_name.strip())

        # 3. Data di nascita (6 caratteri: AA + M + GG)
        data_cf = codicefiscale.encode_birthdate(birth_date_str, gender)

        # 4. Codice comune (4 caratteri)
        # Se è già un codice catastale (es: H501), usalo direttamente
        # Altrimenti converti dal nome
        if len(birth_place_code) == 4 and birth_place_code[0].isalpha():
            codice_comune = birth_place_code
        else:
            codice_comune = codicefiscale.encode_birthplace(birth_place_code)

        # 5. Costruisci il CF senza CIN
        cf_partial = f"{cognome_cf}{nome_cf}{data_cf}{codice_comune}"

        # 6. Calcola il CIN (carattere di controllo)
        cin = codicefiscale.encode_cin(cf_partial)

        # 7. CF completo
        cf_completo = f"{cf_partial}{cin}"

        return cf_completo.upper()

    except Exception as e:
        logger.error(f"Errore calcolo CF: {e}")
        return None


def validate_cf(cf):
    """Valida un codice fiscale esistente."""
    try:
        return codicefiscale.is_valid(cf)
    except Exception:
        return False


def search_municipality(query):
    """
    Cerca un comune per nome o codice catastale.
    """
    try:
        # Prova come codice catastale
        if len(query) == 4 and query.isalpha():
            # Non c'è funzione diretta, ma encode_birthplace accetta codici
            try:
                result = codicefiscale.encode_birthplace(query.upper())
                if result:
                    return [{"code": result, "name": query.upper()}]
            except Exception:
                pass

        # Cerca per nome
        try:
            code = codicefiscale.encode_birthplace(query)
            if code:
                return [{"code": code, "name": query}]
        except Exception:
            pass

        return []

    except Exception as e:
        logger.error(f"Errore ricerca comune: {e}")
        return []