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

import json
import os
from django.conf import settings

COMUNI_CACHE = None


def load_comuni_json():
    """
    Carica il file comuni_cf.json UNA SOLA VOLTA (cache in memoria)
    """
    global COMUNI_CACHE

    if COMUNI_CACHE is not None:
        return COMUNI_CACHE

    path = os.path.join(
        settings.BASE_DIR,
        "accounts",
        "data",
        "comuni_cf.json"
    )

    try:
        with open(path, "r", encoding="utf-8") as f:
            COMUNI_CACHE = json.load(f)
            return COMUNI_CACHE
    except Exception as e:
        print(f"Errore caricamento comuni: {e}")
        COMUNI_CACHE = []
        return []

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